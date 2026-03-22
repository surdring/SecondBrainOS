"""
Cross-Encoder 重排任务实现 - 4.1.2

功能：
1. 异步 rerank 任务（独立超时与并发控制）
2. 降级回 fusion 排序并记录审计日志
3. 混合评分（rerank 分数加权融合）
4. 符号查询保护（对高 BM25/lexical 命中设置保底阈值）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sbo_core.tasks_framework import task_wrapper, enqueue_task, QUEUE_RERANK, TaskPriority
from sbo_core.audit import audit_log
from sbo_core.config import load_settings
from sbo_core.errors import ErrorCode, AppError
from sbo_core.rerank_client import RerankClient, RerankResult

_logger = logging.getLogger("sbo_core.rerank_tasks")


@dataclass
class RerankCandidate:
    """重排候选"""
    evidence_id: str
    text: str
    source: str
    occurred_at: datetime
    scores: dict[str, float]
    original_rank: int


@dataclass
class RerankTaskResult:
    """重排任务结果"""
    candidates: list[RerankCandidate]
    rerank_applied: bool
    fallback_reason: str | None
    provider_used: str | None
    model_used: str | None
    processing_time_ms: int


@dataclass
class HybridScoreConfig:
    """混合评分配置"""
    rerank_weight: float = 0.5  # rerank 分数权重
    preserve_original: bool = True  # 不完全覆盖原始相关性
    lexical_preservation_floor: float = 0.35  # 符号查询保底阈值
    symbolic_lexical_threshold: float = 0.6  # 触发保底的高 BM25 阈值


class RerankTaskService:
    """重排任务服务"""
    
    def __init__(self):
        self._config = HybridScoreConfig()
        self._semaphore: asyncio.Semaphore | None = None
    
    def _get_semaphore(self) -> asyncio.Semaphore:
        """获取并发控制信号量（单实例最多 5 个并发重排请求）"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(5)
        return self._semaphore
    
    async def execute_rerank_task(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        is_symbolic: bool = False,
    ) -> RerankTaskResult:
        """
        执行重排任务
        
        Args:
            query: 查询字符串
            candidates: 候选列表（fusion 后的结果）
            is_symbolic: 是否为符号查询
            
        Returns:
            RerankTaskResult 包含重排结果和降级信息
        """
        start_time = datetime.now(timezone.utc)
        settings = load_settings()
        
        if not settings.rerank_provider_url:
            # 没有配置重排服务，直接返回原始候选
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason="rerank_not_configured",
                provider_used=None,
                model_used=None,
                processing_time_ms=0,
            )
        
        # 限制候选数量
        max_candidates = settings.rerank_max_candidates
        limited_candidates = candidates[:max_candidates]
        
        # 转换为内部格式
        rerank_candidates = [
            self._dict_to_candidate(c, i) for i, c in enumerate(limited_candidates)
        ]
        
        provider_used = settings.rerank_provider_url
        model_used = settings.rerank_model_id or "default"
        
        try:
            # 使用信号量控制并发
            async with self._get_semaphore():
                client = RerankClient(
                    base_url=settings.rerank_provider_url,
                    api_key=settings.rerank_api_key,
                    timeout_ms=settings.rerank_timeout_ms,
                )
                
                payload_candidates = [
                    {
                        "evidence_id": c.evidence_id,
                        "text": c.text,
                        "source": c.source,
                        "occurred_at": c.occurred_at.isoformat(),
                        "scores": c.scores,
                    }
                    for c in rerank_candidates
                ]
                
                results = await client.rerank(
                    query=query,
                    candidates=payload_candidates,
                    model=settings.rerank_model_id or None,
                )
            
            # 应用混合评分
            reranked_candidates = self._apply_hybrid_scoring(
                rerank_candidates, results, is_symbolic, settings.rerank_weight
            )
            
            # 保持未参与重排的候选
            if len(candidates) > len(limited_candidates):
                remaining = [
                    self._dict_to_candidate(c, i + len(limited_candidates))
                    for i, c in enumerate(candidates[len(limited_candidates):])
                ]
                reranked_candidates.extend(remaining)
            
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            # 审计日志
            audit_log(
                event="rerank.task",
                outcome="success",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "candidates_in": len(limited_candidates),
                    "candidates_out": len(results),
                    "duration_ms": duration_ms,
                    "is_symbolic": is_symbolic,
                }
            )
            
            return RerankTaskResult(
                candidates=reranked_candidates,
                rerank_applied=True,
                fallback_reason=None,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
            )
            
        except AppError as e:
            # 重排失败，降级到 fusion 结果
            fallback_reason = self._classify_fallback_reason(e)
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            _logger.warning(
                f"Rerank failed, falling back to fusion: {e.message} (reason={fallback_reason})"
            )
            
            # 审计日志记录降级
            audit_log(
                event="rerank.task",
                outcome="degrade",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "fallback_reason": fallback_reason,
                    "error_code": e.code if hasattr(e, 'code') else None,
                    "error_message": e.message if hasattr(e, 'message') else str(e),
                    "duration_ms": duration_ms,
                }
            )
            
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason=fallback_reason,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
            )
        
        except Exception as e:
            # 意外错误，降级
            fallback_reason = "unexpected_error"
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            _logger.error(f"Rerank unexpected error: {e}")
            
            audit_log(
                event="rerank.task",
                outcome="degrade",
                details={
                    "provider": provider_used,
                    "model": model_used,
                    "fallback_reason": fallback_reason,
                    "error": str(e),
                    "duration_ms": duration_ms,
                }
            )
            
            return RerankTaskResult(
                candidates=[self._dict_to_candidate(c, i) for i, c in enumerate(candidates)],
                rerank_applied=False,
                fallback_reason=fallback_reason,
                provider_used=provider_used,
                model_used=model_used,
                processing_time_ms=duration_ms,
            )
    
    def _apply_hybrid_scoring(
        self,
        candidates: list[RerankCandidate],
        rerank_results: list[RerankResult],
        is_symbolic: bool,
        rerank_weight: float,
    ) -> list[RerankCandidate]:
        """
        应用混合评分策略
        
        混合公式：final_score = (1 - w) * fusion_score + w * rerank_score
        
        符号查询保护：
        - 如果原始 BM25/lexical 分数 >= threshold，设置保底 floor
        """
        rerank_map: dict[str, float] = {r.evidence_id: r.score for r in rerank_results}
        
        for candidate in candidates:
            fusion_score = candidate.scores.get("fusion_score", 0.0)
            
            if candidate.evidence_id in rerank_map:
                rerank_score = rerank_map[candidate.evidence_id]
                
                # 混合评分（rerank 不完全覆盖原始相关性）
                final_score = (1.0 - rerank_weight) * fusion_score + rerank_weight * rerank_score
                
                # 符号查询保护：高 BM25 命中设置保底阈值
                if is_symbolic:
                    bm25_score = candidate.scores.get("bm25_score", 0.0)
                    lexical_score = candidate.scores.get("lexical_score", bm25_score)
                    
                    if lexical_score >= self._config.symbolic_lexical_threshold:
                        final_score = max(final_score, self._config.lexical_preservation_floor)
                        candidate.scores["preservation_floor_applied"] = 1.0
                
                candidate.scores["rerank_score"] = rerank_score
                candidate.scores["fusion_score"] = fusion_score
                candidate.scores["hybrid_score"] = final_score
                candidate.scores["rerank_weight"] = rerank_weight
            else:
                # 未参与重排的候选保持原分数
                final_score = fusion_score
                candidate.scores["rerank_missing"] = 1.0
            
            candidate.scores["final_score"] = final_score
        
        # 按最终分数排序
        candidates.sort(key=lambda x: x.scores.get("final_score", 0.0), reverse=True)
        
        return candidates
    
    def _classify_fallback_reason(self, error: AppError) -> str:
        """分类降级原因"""
        code = getattr(error, 'code', None)
        message = getattr(error, 'message', str(error)).lower()
        details = getattr(error, 'details', {})
        
        if code == ErrorCode.RERANK_FAILED:
            if "timeout" in message:
                return "timeout"
            elif "unavailable" in message or "server error" in message:
                return "5xx"
            elif "5" in str(details.get("status_code", "")):
                return "5xx"
            elif "auth" in message:
                return "auth_failed"
        
        return "provider_error"
    
    def _dict_to_candidate(self, data: dict[str, Any], rank: int) -> RerankCandidate:
        """将字典转换为 RerankCandidate"""
        occurred_at_str = data.get("occurred_at", datetime.now(timezone.utc).isoformat())
        if isinstance(occurred_at_str, str):
            occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
        else:
            occurred_at = datetime.now(timezone.utc)
        
        return RerankCandidate(
            evidence_id=data.get("evidence_id", ""),
            text=data.get("text", ""),
            source=data.get("source", ""),
            occurred_at=occurred_at,
            scores=data.get("scores", {}),
            original_rank=rank,
        )


# 全局服务实例
rerank_service = RerankTaskService()


@task_wrapper(max_retries=2, timeout=300)  # 5 分钟超时，最多重试 2 次
def rerank_candidates_task(
    query: str,
    candidates: list[dict[str, Any]],
    is_symbolic: bool = False,
) -> dict[str, Any]:
    """
    RQ 异步重排任务
    
    该任务可以异步执行重排，适用于：
    - 离线重排优化
    - 批量文档重排
    - 预热缓存
    
    Args:
        query: 查询字符串
        candidates: fusion 后的候选列表
        is_symbolic: 是否为符号查询
        
    Returns:
        重排结果字典
    """
    import asyncio
    
    result = asyncio.run(rerank_service.execute_rerank_task(query, candidates, is_symbolic))
    
    return {
        "candidates": [
            {
                "evidence_id": c.evidence_id,
                "text": c.text,
                "source": c.source,
                "occurred_at": c.occurred_at.isoformat(),
                "scores": c.scores,
                "original_rank": c.original_rank,
            }
            for c in result.candidates
        ],
        "rerank_applied": result.rerank_applied,
        "fallback_reason": result.fallback_reason,
        "provider_used": result.provider_used,
        "model_used": result.model_used,
        "processing_time_ms": result.processing_time_ms,
    }


def enqueue_rerank_task(
    query: str,
    candidates: list[dict[str, Any]],
    is_symbolic: bool = False,
    job_id: str | None = None,
) -> Any:
    """
    将重排任务入队
    
    Args:
        query: 查询字符串
        candidates: 候选列表
        is_symbolic: 是否为符号查询
        job_id: 自定义 job ID
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        rerank_candidates_task,
        query,
        candidates,
        is_symbolic,
        queue_name=QUEUE_RERANK,
        priority=TaskPriority.HIGH,
        job_id=job_id,
        timeout=300,  # 5 分钟
        max_retries=2,
        retry_intervals=[10, 30],  # 10 秒、30 秒后重试
    )
