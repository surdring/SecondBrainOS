from __future__ import annotations

import asyncio
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from sbo_core.audit import audit_log
from sbo_core.database import get_database, RawEvent
from sbo_core.config import load_settings
from sbo_core.degradation import DegradationStrategy
from sbo_core.models import Evidence, EvidenceType
from sbo_core.errors import AppError, ErrorCode, WeKnoraError, rerank_failed, retrieval_failed
from sbo_core.rerank_client import RerankClient
from sbo_core.weknora_client import WeKnoraClient


class RetrievalCandidate:
    """检索候选项"""
    
    def __init__(
        self,
        evidence_id: str,
        text: str,
        occurred_at: datetime,
        source: str,
        evidence_type: EvidenceType,
        scores: Dict[str, float],
        refs: Dict[str, Any]
    ):
        self.evidence_id = evidence_id
        self.text = text
        self.occurred_at = occurred_at
        self.source = source
        self.evidence_type = evidence_type
        self.scores = scores
        self.refs = refs
        self.final_score = 0.0
    
    def to_evidence(self) -> Evidence:
        """转换为 Evidence 对象"""
        return Evidence(
            evidence_id=self.evidence_id,
            type=self.evidence_type.value,
            text=self.text,
            occurred_at=self.occurred_at,
            source=self.source,
            confidence=self.final_score,
            refs=self.refs,
            scores=self.scores
        )


class RetrievalPipeline:
    """检索排序管线"""
    
    def __init__(self):
        self.db = None
        self._weknora_transport = None
        self._rerank_transport = None
        
        # 配置参数
        self.hard_min_score = 0.3
        self.semantic_weight = 0.7
        self.bm25_weight = 0.3
        self.symbolic_lexical_threshold = 0.6
        self.preservation_floor = 0.35
        self.time_decay_rate = 0.1  # 每天衰减率
        self.time_weight = 0.2
        self.noise_threshold = 0.1
        self.mmr_lambda = 0.7  # MMR 多样性参数

        # shouldSkipRetrieval 召回护栏（可配置）
        self.skip_deep_min_length = 6
        self.skip_deep_cjk_min_length = 4
        self.skip_deep_exact = {"ok", "okay", "k", "thanks", "thank you", "thx", "hi", "hello", "hey"}
        self.skip_deep_contains = {"谢谢", "好的", "嗯", "哈", "哈哈", "收到", "明白", "行"}
        self.skip_deep_emojis = {"🙂", "😊", "👍", "👌", "😂", "🤣", "🙏", "✅", "❌", "❤️", "❤"}

        self.force_deep_contains = {"记得", "之前", "上次", "回顾", "查历史", "历史", "根据文档", "文档", "我说过", "我提到", "我们讨论", "你说过"}
        
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def process(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "fast",
        time_range: Optional[Tuple[datetime, datetime]] = None,
        user_id: Optional[str] = None
    ) -> Tuple[List[Evidence], List[str]]:
        """
        处理检索请求
        
        Args:
            query: 查询字符串
            top_k: 返回结果数量
            mode: 查询模式 (fast/deep)
            time_range: 时间范围过滤
            user_id: 用户ID
            
        Returns:
            (evidence_list, degraded_services)
        """
        start_time = time.time()
        degraded_services = []
        
        try:
            is_symbolic = self._is_symbolic_query(query)

            effective_mode = mode
            if mode == "deep":
                forced = self._should_force_deep_retrieval(query)
                if not forced:
                    should_skip, reason = self._should_skip_deep_retrieval(query)
                    if should_skip:
                        effective_mode = "fast"
                        degraded_services.append(f"skip_deep_retrieval:{reason}")

            # 1. 候选召回（可并行）
            candidates = await self._candidate_recall(
                query, effective_mode, time_range, user_id, degraded_services
            )
            
            # 2. 融合（fusion）
            fused_candidates = self._fusion(candidates, is_symbolic=is_symbolic)
            
            # 3. 可选 rerank
            reranked_candidates = await self._optional_rerank(
                query, fused_candidates, degraded_services, is_symbolic=is_symbolic
            )
            
            # 4. 归一化与过滤
            normalized_candidates = self._normalization_and_filter(reranked_candidates)
            
            # 5. 时间与生命周期重排
            time_reranked_candidates = self._time_lifecycle_rerank(normalized_candidates)
            
            # 6. 噪声过滤与多样性
            final_candidates = self._noise_filter_and_diversity(time_reranked_candidates)

            for c in final_candidates:
                c.scores["final_score"] = c.final_score
            
            # 7. 转换为 Evidence 对象并截取 top_k
            evidence_list = [c.to_evidence() for c in final_candidates[:top_k]]
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return evidence_list, degraded_services
            
        except Exception as e:
            if isinstance(e, AppError):
                raise
            raise retrieval_failed(f"Retrieval pipeline failed: {str(e)}")
    
    async def _candidate_recall(
        self,
        query: str,
        mode: str,
        time_range: Optional[Tuple[datetime, datetime]],
        user_id: Optional[str],
        degraded_services: List[str]
    ) -> List[RetrievalCandidate]:
        """候选召回（可并行）"""
        tasks = []
        
        # Semantic 召回
        tasks.append(self._semantic_recall(query, time_range, user_id))
        
        # Episodic 召回（仅在 deep 模式）
        if mode == "deep":
            tasks.append(self._episodic_recall(query, time_range, user_id, degraded_services))
        
        # Graph 召回（可选，暂不实现）
        # if mode == "deep":
        #     tasks.append(self._graph_recall(query, time_range, user_id, degraded_services))
        
        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        candidates = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if i == 1:  # Episodic 召回失败
                    degraded_services.append("weknora_recall")
                continue
            candidates.extend(result)
        
        return candidates
    
    async def _semantic_recall(
        self,
        query: str,
        time_range: Optional[Tuple[datetime, datetime]],
        user_id: Optional[str]
    ) -> List[RetrievalCandidate]:
        """Semantic 召回（pgvector/结构化事实）"""
        try:
            db = self._get_db()
            session = db.get_session()
            
            # 简化的文本匹配（实际应该使用向量检索）
            query_pattern = f"%{query}%"
            
            events = session.query(RawEvent).filter(
                RawEvent.content.ilike(query_pattern)
            )
            
            # 应用时间范围过滤
            if time_range:
                if time_range[0]:
                    events = events.filter(RawEvent.occurred_at >= time_range[0])
                if time_range[1]:
                    events = events.filter(RawEvent.occurred_at <= time_range[1])
            
            # 应用用户过滤
            if user_id:
                events = events.filter(RawEvent.user_id == user_id)
            
            events = events.order_by(RawEvent.occurred_at.desc()).limit(20).all()
            
            candidates = []
            for event in events:
                # 简化的评分（实际应该使用向量相似度）
                semantic_score = self._calculate_semantic_similarity(query, event.content)
                bm25_score = self._calculate_bm25_score(query, event.content)
                
                candidate = RetrievalCandidate(
                    evidence_id=str(event.id),
                    text=event.content,
                    occurred_at=event.occurred_at,
                    source=event.source,
                    evidence_type=EvidenceType.RAW_EVENT,
                    scores={
                        "semantic_score": semantic_score,
                        "bm25_score": bm25_score
                    },
                    refs={"event_id": str(event.id)}
                )
                candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            raise retrieval_failed(f"Semantic recall failed: {str(e)}")
        finally:
            if 'session' in locals():
                session.close()
    
    async def _episodic_recall(
        self,
        query: str,
        time_range: Optional[Tuple[datetime, datetime]],
        user_id: Optional[str],
        degraded_services: List[str]
    ) -> List[RetrievalCandidate]:
        """Episodic 召回（WeKnora 混合检索）"""
        try:
            settings = load_settings()
            if not settings.weknora_enable:
                return []

            client = WeKnoraClient(
                base_url=settings.weknora_base_url,
                api_key=settings.weknora_api_key,
                timeout_ms=settings.weknora_request_timeout_ms,
                transport=self._weknora_transport,
            )

            results = await client.knowledge_search(
                query=query,
                knowledge_base_id=settings.weknora_knowledge_base_id or None,
                knowledge_base_ids=settings.weknora_knowledge_base_ids,
                request_id=None,
                top_k=settings.weknora_retrieval_top_k,
            )

            threshold = settings.weknora_retrieval_threshold
            if threshold is not None:
                results = [r for r in results if r.score >= threshold]

            now = datetime.now(timezone.utc)
            candidates: list[RetrievalCandidate] = []
            for r in results:
                occurred_at = now
                if r.metadata and isinstance(r.metadata.get("occurred_at"), str):
                    try:
                        occurred_at = datetime.fromisoformat(r.metadata["occurred_at"])  # type: ignore[arg-type]
                        if occurred_at.tzinfo is None:
                            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                    except Exception:
                        occurred_at = now

                days_ago = max((now - occurred_at).days, 0)
                time_score = math.exp(-settings.weknora_time_decay_rate * days_ago)
                final_score = (
                    r.score * settings.weknora_semantic_weight
                    + time_score * settings.weknora_time_weight
                )

                candidate = RetrievalCandidate(
                    evidence_id=r.id,
                    text=r.content,
                    occurred_at=occurred_at,
                    source="weknora",
                    evidence_type=EvidenceType.RAW_EVENT,
                    scores={
                        "weknora_score": r.score,
                        "semantic_score": r.score,
                        "time_score": time_score,
                        "final_score": final_score,
                    },
                    refs={
                        "knowledge_id": r.knowledge_id,
                        "knowledge_title": r.knowledge_title,
                        "chunk_index": r.chunk_index,
                    },
                )
                candidate.final_score = final_score
                candidates.append(candidate)

            candidates.sort(key=lambda x: x.final_score, reverse=True)
            audit_log(
                event="weknora.recall",
                outcome="success",
                details={
                    "query_len": len(query),
                    "results_in": len(results),
                    "candidates_out": len(candidates),
                    "threshold": threshold,
                    "top_k": settings.weknora_retrieval_top_k,
                    "has_kb_id": bool(settings.weknora_knowledge_base_id),
                    "has_kb_ids": bool(settings.weknora_knowledge_base_ids),
                },
            )
            return candidates

        except WeKnoraError as e:
            degraded_services.append(f"weknora_recall:{e.code.value}")
            settings = load_settings()
            if settings.weknora_degradation_strategy == DegradationStrategy.DEGRADE:
                degraded_services.append("weknora_degraded_to_fast")
                audit_log(
                    event="weknora.recall",
                    outcome="degrade",
                    details={
                        "code": e.code.value,
                        "error_type": getattr(e, "error_type", None),
                        "strategy": "degrade",
                    },
                )
                return []
            audit_log(
                event="weknora.recall",
                outcome="fail",
                details={
                    "code": e.code.value,
                    "error_type": getattr(e, "error_type", None),
                    "strategy": "fail",
                },
            )
            raise
    
    def _fusion(
        self,
        candidates: List[RetrievalCandidate],
        *,
        is_symbolic: bool = False,
    ) -> List[RetrievalCandidate]:
        """融合（fusion）：dense 为主，lexical/BM25 命中提供奖励/保底"""
        for candidate in candidates:
            semantic_score = candidate.scores.get("semantic_score", 0.0)
            bm25_score = candidate.scores.get("bm25_score", 0.0)
            candidate.scores.setdefault("dense_score", semantic_score)
            candidate.scores.setdefault("lexical_score", bm25_score)
            
            # dense 为主，BM25 为辅
            fusion_score = (
                self.semantic_weight * semantic_score + 
                self.bm25_weight * bm25_score
            )

            if is_symbolic and bm25_score >= self.symbolic_lexical_threshold:
                fusion_score = max(fusion_score, self.preservation_floor)
                candidate.scores["preservation_floor_applied"] = 1.0
                candidate.scores["preservation_floor"] = self.preservation_floor
            
            candidate.scores["fusion_score"] = fusion_score
            candidate.final_score = fusion_score
        
        return candidates
    
    async def _optional_rerank(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
        degraded_services: List[str],
        *,
        is_symbolic: bool = False,
    ) -> List[RetrievalCandidate]:
        """可选 rerank（cross-encoder 或等价重排）"""
        try:
            settings = load_settings()
            if not settings.rerank_provider_url:
                return candidates

            limited = candidates[: max(1, settings.rerank_max_candidates)]
            provider = RerankClient(
                base_url=settings.rerank_provider_url,
                api_key=settings.rerank_api_key,
                timeout_ms=settings.rerank_timeout_ms,
                transport=self._rerank_transport,
            )

            payload_candidates: list[dict[str, Any]] = []
            for c in limited:
                payload_candidates.append(
                    {
                        "evidence_id": c.evidence_id,
                        "text": c.text,
                        "source": c.source,
                        "occurred_at": c.occurred_at.isoformat(),
                        "scores": c.scores,
                    }
                )

            results = await provider.rerank(
                query=query,
                candidates=payload_candidates,
                model=settings.rerank_model_id or None,
                request_id=None,
            )

            rerank_map: dict[str, float] = {r.evidence_id: r.score for r in results}
            w = settings.rerank_weight
            for c in limited:
                if c.evidence_id in rerank_map:
                    rerank_score = rerank_map[c.evidence_id]
                    c.scores["rerank_score"] = rerank_score
                    c.final_score = (1.0 - w) * c.final_score + w * rerank_score
                    c.scores["rerank_weight"] = w
                    c.scores["rerank_fused_score"] = c.final_score
                else:
                    c.scores["rerank_missing"] = 1.0

                bm25_score = c.scores.get("bm25_score", 0.0)
                if is_symbolic and bm25_score >= self.symbolic_lexical_threshold:
                    c.final_score = max(c.final_score, self.preservation_floor)
                    c.scores["preservation_floor_applied"] = 1.0
                    c.scores["preservation_floor"] = self.preservation_floor

            audit_log(
                event="rerank.call",
                outcome="success",
                details={
                    "provider_url": settings.rerank_provider_url,
                    "model": settings.rerank_model_id or None,
                    "timeout_ms": settings.rerank_timeout_ms,
                    "weight": settings.rerank_weight,
                    "candidates_in": len(limited),
                    "results_out": len(results),
                },
            )

            return candidates
            
        except Exception as e:
            # rerank 失败必须降级到 fusion 结果
            degraded_services.append("rerank_provider")
            audit_log(
                event="rerank.call",
                outcome="degrade",
                details={
                    "error": str(e),
                },
            )
            return candidates

    def _is_symbolic_query(self, query: str) -> bool:
        q = query.strip()
        if not q:
            return False

        if any(ch in q for ch in ["_", "-", "/", ".", ":", "=", "@"]):
            return True
        if q.upper() == q and any(c.isalpha() for c in q):
            return True
        if any(c.isdigit() for c in q):
            return True

        return False

    def _should_force_deep_retrieval(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return False

        for kw in self.force_deep_contains:
            if kw.lower() in q:
                return True

        return False

    def _should_skip_deep_retrieval(self, query: str) -> tuple[bool, str]:
        q = query.strip()
        if not q:
            return True, "empty"

        q_lower = q.lower()

        if q_lower in self.skip_deep_exact:
            return True, "smalltalk_exact"

        if any(e in q for e in self.skip_deep_emojis):
            if len(q) <= 4:
                return True, "emoji_short"

        for kw in self.skip_deep_contains:
            if kw in q:
                if len(q) <= 6:
                    return True, "smalltalk_contains"

        if self._is_cjk(q):
            if len(q) < self.skip_deep_cjk_min_length:
                return True, "cjk_too_short"
        else:
            if len(q) < self.skip_deep_min_length:
                return True, "too_short"

        if q_lower in {"?", "？"}:
            return True, "punct_only"

        return False, ""

    def _is_cjk(self, text: str) -> bool:
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                return True
        return False
    
    def _normalization_and_filter(self, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        """归一化与过滤：length normalization + hardMinScore"""
        # 1. Length normalization
        for candidate in candidates:
            text_length = len(candidate.text)
            # 长文本惩罚
            length_penalty = 1.0 / (1.0 + math.log(max(text_length, 1)))
            candidate.final_score *= length_penalty
            candidate.scores["length_penalty"] = length_penalty
        
        # 2. HardMinScore 硬过滤
        filtered_candidates = [
            c for c in candidates 
            if c.final_score >= self.hard_min_score
        ]
        
        return filtered_candidates
    
    def _time_lifecycle_rerank(self, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        """时间与生命周期重排：time-decay / recency boost"""
        now = datetime.now(timezone.utc)
        
        for candidate in candidates:
            # 计算时间衰减
            days_ago = (now - candidate.occurred_at).days
            time_weight = math.exp(-self.time_decay_rate * days_ago)
            
            # 时间重排：final_score = semantic_score * semantic_weight + time_weight * time_weight
            original_score = candidate.final_score
            time_reranked_score = (
                original_score * (1 - self.time_weight) + 
                time_weight * self.time_weight
            )
            
            candidate.final_score = time_reranked_score
            candidate.scores["time_weight"] = time_weight
            candidate.scores["time_reranked_score"] = time_reranked_score
        
        return candidates
    
    def _noise_filter_and_diversity(self, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        """噪声过滤与多样性：noise filter + MMR diversity"""
        # 1. 噪声过滤
        filtered_candidates = [
            c for c in candidates 
            if c.final_score >= self.noise_threshold
        ]
        
        # 2. MMR diversity（最大边际相关性）
        if not filtered_candidates:
            return []
        
        # 按分数排序
        filtered_candidates.sort(key=lambda x: x.final_score, reverse=True)
        
        # MMR 算法
        selected = [filtered_candidates[0]]
        remaining = filtered_candidates[1:]
        
        while remaining and len(selected) < 10:  # 限制候选数量
            best_candidate = None
            best_mmr_score = -1
            
            for candidate in remaining:
                # 计算与已选候选的最大相似度
                max_similarity = 0
                for selected_candidate in selected:
                    similarity = self._calculate_text_similarity(
                        candidate.text, selected_candidate.text
                    )
                    max_similarity = max(max_similarity, similarity)
                
                # MMR 分数 = λ * relevance - (1-λ) * max_similarity
                mmr_score = (
                    self.mmr_lambda * candidate.final_score - 
                    (1 - self.mmr_lambda) * max_similarity
                )
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_candidate = candidate
            
            if best_candidate:
                selected.append(best_candidate)
                remaining.remove(best_candidate)
            else:
                break
        
        # 按最终分数重新排序
        selected.sort(key=lambda x: x.final_score, reverse=True)
        
        return selected
    
    def _calculate_semantic_similarity(self, query: str, text: str) -> float:
        """计算语义相似度（简化版本）"""
        # 简化的文本相似度计算
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        
        if not query_words or not text_words:
            return 0.0
        
        intersection = query_words.intersection(text_words)
        union = query_words.union(text_words)
        
        jaccard_similarity = len(intersection) / len(union)
        
        # 添加一些随机性模拟向量相似度
        return jaccard_similarity * (0.7 + 0.6 * random.random())
    
    def _calculate_bm25_score(self, query: str, text: str) -> float:
        """计算 BM25 分数（简化版本）"""
        # 简化的 BM25 计算
        query_words = query.lower().split()
        text_words = text.lower().split()
        
        if not query_words:
            return 0.0
        
        score = 0.0
        text_len = len(text_words)
        
        for word in query_words:
            if word in text_words:
                # 简化的 TF-IDF 计算
                tf = text_words.count(word) / text_len
                idf = 1.0  # 简化，实际应该计算 IDF
                score += tf * idf
        
        # 归一化
        return min(score / len(query_words), 1.0)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（用于 MMR）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)


# 全局检索管线实例
retrieval_pipeline = RetrievalPipeline()
