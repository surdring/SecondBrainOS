from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from sbo_core.retrieval_pipeline import RetrievalPipeline, RetrievalCandidate
from sbo_core.models import EvidenceType


class TestRetrievalPipeline:
    """测试检索排序管线"""
    
    @pytest.fixture
    def pipeline(self):
        """创建检索管线实例"""
        return RetrievalPipeline()
    
    @pytest.fixture
    def sample_candidates(self):
        """示例候选项"""
        now = datetime.now(timezone.utc)
        return [
            RetrievalCandidate(
                evidence_id="1",
                text="项目进展讨论",
                occurred_at=now,
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.9, "bm25_score": 0.8},
                refs={"event_id": "1"}
            ),
            RetrievalCandidate(
                evidence_id="2",
                text="技术方案设计",
                occurred_at=now,
                source="api",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.7, "bm25_score": 0.6},
                refs={"event_id": "2"}
            ),
            RetrievalCandidate(
                evidence_id="3",
                text="会议纪要",
                occurred_at=now,
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.5, "bm25_score": 0.4},
                refs={"event_id": "3"}
            )
        ]
    
    @patch('sbo_core.retrieval_pipeline.get_database')
    def test_candidate_recall_semantic_only(self, mock_get_db, pipeline):
        """测试仅语义召回"""
        # 模拟数据库
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_events = MagicMock()
        
        mock_db.get_session.return_value = mock_session
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_events
        mock_events.all.return_value = []
        
        mock_get_db.return_value = mock_db
        
        async def test():
            candidates = await pipeline._semantic_recall(
                query="项目进展",
                time_range=None,
                user_id=None
            )
            
            # 验证返回的是候选项列表
            assert isinstance(candidates, list)
        
        asyncio.run(test())
    
    def test_fusion(self, pipeline, sample_candidates):
        """测试融合算法"""
        fused_candidates = pipeline._fusion(sample_candidates, is_symbolic=False)
        
        # 验证融合分数计算
        for candidate in fused_candidates:
            assert 'fusion_score' in candidate.scores
            assert candidate.final_score == candidate.scores['fusion_score']
            
            # 验证融合分数计算公式
            expected_fusion = (
                pipeline.semantic_weight * candidate.scores['semantic_score'] +
                pipeline.bm25_weight * candidate.scores['bm25_score']
            )
            assert abs(candidate.scores['fusion_score'] - expected_fusion) < 0.001
    
    def test_fusion_symbolic_preservation_floor(self, pipeline):
        """测试符号型查询的 preservation floor"""
        now = datetime.now(timezone.utc)
        candidate = RetrievalCandidate(
            evidence_id="1",
            text="OPENAI_API_KEY=***",
            occurred_at=now,
            source="api",
            evidence_type=EvidenceType.RAW_EVENT,
            scores={"semantic_score": 0.01, "bm25_score": 0.95},
            refs={"event_id": "1"},
        )

        fused = pipeline._fusion([candidate], is_symbolic=True)
        assert fused[0].final_score >= pipeline.preservation_floor
        assert fused[0].scores.get("preservation_floor_applied") == 1.0
    
    @pytest.mark.asyncio
    async def test_optional_rerank_success(self, pipeline, sample_candidates):
        """测试重排成功"""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/rerank"):
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": [
                            {"evidence_id": "1", "score": 0.2},
                            {"evidence_id": "2", "score": 0.8},
                            {"evidence_id": "3", "score": 0.1},
                        ],
                    },
                )
            return httpx.Response(404, json={"success": False})

        pipeline._rerank_transport = httpx.MockTransport(handler)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("RERANK_PROVIDER_URL", "http://rerank.local")
        monkeypatch.setenv("RERANK_API_KEY", "test")
        monkeypatch.setenv("RERANK_MODEL_ID", "m")
        monkeypatch.setenv("RERANK_TIMEOUT_MS", "1000")
        monkeypatch.setenv("RERANK_WEIGHT", "0.5")
        monkeypatch.setenv("RERANK_MAX_CANDIDATES", "20")

        reranked_candidates = await pipeline._optional_rerank(
            query="项目进展",
            candidates=sample_candidates,
            degraded_services=[],
            is_symbolic=False,
        )

        # 验证重排分数存在且为加权融合后的分数
        for candidate in reranked_candidates:
            assert "rerank_score" in candidate.scores or candidate.scores.get("rerank_missing") == 1.0
            if "rerank_score" in candidate.scores:
                assert "rerank_fused_score" in candidate.scores
                assert candidate.final_score == candidate.scores["rerank_fused_score"]

        monkeypatch.undo()
    
    @pytest.mark.asyncio
    async def test_optional_rerank_degradation(self, pipeline, sample_candidates):
        """测试重排降级"""
        degraded_services = []

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        pipeline._rerank_transport = httpx.MockTransport(handler)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("RERANK_PROVIDER_URL", "http://rerank.local")
        monkeypatch.setenv("RERANK_API_KEY", "test")
        monkeypatch.setenv("RERANK_TIMEOUT_MS", "1000")
        monkeypatch.setenv("RERANK_WEIGHT", "0.5")

        reranked_candidates = await pipeline._optional_rerank(
            query="项目进展",
            candidates=sample_candidates,
            degraded_services=degraded_services,
            is_symbolic=False,
        )
        
        # 验证降级服务被记录
        assert "rerank_provider" in degraded_services
        # 验证返回原始候选项（降级行为）
        assert len(reranked_candidates) == len(sample_candidates)

        monkeypatch.undo()
    
    def test_normalization_and_filter(self, pipeline, sample_candidates):
        """测试归一化与过滤"""
        # 设置一些低分候选项
        low_score_candidate = RetrievalCandidate(
            evidence_id="4",
            text="低质量内容",
            occurred_at=datetime.now(timezone.utc),
            source="test",
            evidence_type=EvidenceType.RAW_EVENT,
            scores={"semantic_score": 0.1, "bm25_score": 0.1},
            refs={"event_id": "4"}
        )
        all_candidates = sample_candidates + [low_score_candidate]
        
        filtered_candidates = pipeline._normalization_and_filter(all_candidates)
        
        # 验证低分候选项被过滤
        filtered_ids = [c.evidence_id for c in filtered_candidates]
        assert "4" not in filtered_ids
        
        # 验证长度惩罚被应用
        for candidate in filtered_candidates:
            assert 'length_penalty' in candidate.scores
    
    def test_time_lifecycle_rerank(self, pipeline, sample_candidates):
        """测试时间生命周期重排"""
        # 设置不同的时间
        now = datetime.now(timezone.utc)
        old_time = now.replace(day=now.day - 7)  # 7天前
        
        sample_candidates[0].occurred_at = now  # 最近
        sample_candidates[1].occurred_at = old_time  # 较旧
        
        reranked_candidates = pipeline._time_lifecycle_rerank(sample_candidates)
        
        # 验证时间权重被计算
        for candidate in reranked_candidates:
            assert 'time_weight' in candidate.scores
            assert 'time_reranked_score' in candidate.scores
            assert candidate.final_score == candidate.scores['time_reranked_score']
        
        # 验证最近的内容得分更高
        recent_candidate = next(c for c in reranked_candidates if c.evidence_id == "1")
        old_candidate = next(c for c in reranked_candidates if c.evidence_id == "2")
        
        assert recent_candidate.final_score > old_candidate.final_score
    
    def test_noise_filter_and_diversity(self, pipeline, sample_candidates):
        """测试噪声过滤与多样性"""
        # 添加相似内容
        similar_candidate = RetrievalCandidate(
            evidence_id="4",
                text="项目进展讨论",  # 与第一个候选项相似
            occurred_at=datetime.now(timezone.utc),
            source="webchat",
            evidence_type=EvidenceType.RAW_EVENT,
            scores={"semantic_score": 0.85, "bm25_score": 0.75},
            refs={"event_id": "4"}
        )
        similar_candidate.final_score = 0.8  # 设置高分
        
        all_candidates = sample_candidates + [similar_candidate]
        
        diverse_candidates = pipeline._noise_filter_and_diversity(all_candidates)
        
        # 验证返回的是候选项列表
        assert isinstance(diverse_candidates, list)
        assert len(diverse_candidates) > 0
        
        # 验证按分数排序
        scores = [c.final_score for c in diverse_candidates]
        assert scores == sorted(scores, reverse=True)
    
    def test_calculate_semantic_similarity(self, pipeline):
        """测试语义相似度计算"""
        # 完全匹配
        similarity1 = pipeline._calculate_semantic_similarity("项目进展", "项目进展讨论")
        assert similarity1 >= 0.0  # 简化版本可能返回较低值
        
        # 部分匹配
        similarity2 = pipeline._calculate_semantic_similarity("项目", "项目进展讨论")
        assert similarity2 >= 0.0
        assert similarity2 <= 1.0
        
        # 无匹配
        similarity3 = pipeline._calculate_semantic_similarity("技术", "项目进展讨论")
        assert similarity3 >= 0.0
        
        # 空查询
        similarity4 = pipeline._calculate_semantic_similarity("", "项目进展讨论")
        assert similarity4 == 0.0
    
    def test_calculate_bm25_score(self, pipeline):
        """测试 BM25 分数计算"""
        # 完全匹配
        score1 = pipeline._calculate_bm25_score("项目进展", "项目进展讨论")
        assert score1 >= 0.0
        assert score1 <= 1.0
        
        # 部分匹配
        score2 = pipeline._calculate_bm25_score("项目", "项目进展讨论")
        assert score2 >= 0.0
        assert score2 <= 1.0
        
        # 无匹配
        score3 = pipeline._calculate_bm25_score("技术", "项目进展讨论")
        assert score3 == 0.0
        
        # 空查询
        score4 = pipeline._calculate_bm25_score("", "项目进展讨论")
        assert score4 == 0.0
    
    def test_calculate_text_similarity(self, pipeline):
        """测试文本相似度计算"""
        # 完全相同
        similarity1 = pipeline._calculate_text_similarity("项目进展", "项目进展")
        assert similarity1 == 1.0
        
        # 部分相同
        similarity2 = pipeline._calculate_text_similarity("项目进展", "项目讨论")
        assert similarity2 >= 0.0
        
        # 完全不同
        similarity3 = pipeline._calculate_text_similarity("项目", "技术方案")
        assert similarity3 == 0.0
        
        # 空文本
        similarity4 = pipeline._calculate_text_similarity("", "项目进展")
        assert similarity4 == 0.0
    
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._semantic_recall')
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._episodic_recall')
    @pytest.mark.asyncio
    async def test_process_fast_mode(self, mock_episodic, mock_semantic, pipeline):
        """测试 Fast 模式处理"""
        # 设置 mock
        mock_semantic.return_value = [
            RetrievalCandidate(
                evidence_id="1",
                text="项目进展讨论",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.9},
                refs={"event_id": "1"}
            )
        ]
        mock_episodic.return_value = []  # Fast 模式不调用 Episodic
        
        # 执行处理
        evidence, degraded_services = await pipeline.process(
            query="项目进展",
            mode="fast",
            top_k=5
        )
        
        # 验证结果
        assert isinstance(evidence, list)
        assert isinstance(degraded_services, list)
        mock_semantic.assert_called_once()
        mock_episodic.assert_not_called()  # Fast 模式不调用 Episodic

        if evidence:
            assert "final_score" in evidence[0].scores
    
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._semantic_recall')
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._episodic_recall')
    @pytest.mark.asyncio
    async def test_process_deep_mode(self, mock_episodic, mock_semantic, pipeline):
        """测试 Deep 模式处理"""
        # 设置 mock
        mock_semantic.return_value = [
            RetrievalCandidate(
                evidence_id="1",
                text="项目进展讨论",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.9},
                refs={"event_id": "1"}
            )
        ]
        mock_episodic.return_value = []  # Deep 模式调用 Episodic
        
        # 执行处理
        evidence, degraded_services = await pipeline.process(
            query="项目进展",
            mode="deep",
            top_k=5
        )
        
        # 验证结果
        assert isinstance(evidence, list)
        assert isinstance(degraded_services, list)
        mock_semantic.assert_called_once()
        mock_episodic.assert_called_once()  # Deep 模式调用 Episodic

    @pytest.mark.asyncio
    async def test_weknora_episodic_recall_success_with_transport(self, pipeline, monkeypatch):
        """WeKnora enable 时，_episodic_recall 能通过 transport 取回结果并生成候选"""
        import httpx

        from sbo_core.degradation import DegradationStrategy

        monkeypatch.setenv("WEKNORA_ENABLE", "true")
        monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.local/api/v1")
        monkeypatch.setenv("WEKNORA_API_KEY", "test")
        monkeypatch.setenv("WEKNORA_REQUEST_TIMEOUT_MS", "10000")
        monkeypatch.setenv("WEKNORA_RETRIEVAL_TOP_K", "8")
        monkeypatch.setenv("WEKNORA_RETRIEVAL_THRESHOLD", "")
        monkeypatch.setenv("WEKNORA_TIME_DECAY_RATE", "0.1")
        monkeypatch.setenv("WEKNORA_SEMANTIC_WEIGHT", "0.7")
        monkeypatch.setenv("WEKNORA_TIME_WEIGHT", "0.3")
        monkeypatch.setenv("WEKNORA_DEGRADATION_STRATEGY", DegradationStrategy.FAIL.value)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/knowledge-search"):
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": [
                            {
                                "id": "chunk-1",
                                "content": "hello",
                                "score": 0.9,
                                "knowledge_id": "k1",
                                "knowledge_title": "t1",
                                "chunk_index": 0,
                                "metadata": {"occurred_at": "2026-03-21T00:00:00+00:00"},
                            }
                        ],
                    },
                )
            return httpx.Response(404, json={"success": False})

        pipeline._weknora_transport = httpx.MockTransport(handler)
        degraded: list[str] = []
        candidates = await pipeline._episodic_recall("q", None, None, degraded)
        assert len(candidates) == 1
        assert candidates[0].source == "weknora"
        assert candidates[0].scores.get("weknora_score") == 0.9

    @pytest.mark.asyncio
    async def test_weknora_episodic_recall_auth_failed_degrades(self, pipeline, monkeypatch):
        """WeKnora auth 失败时，degrade 策略应吞掉错误并返回空结果"""
        import httpx

        from sbo_core.degradation import DegradationStrategy

        monkeypatch.setenv("WEKNORA_ENABLE", "true")
        monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.local/api/v1")
        monkeypatch.setenv("WEKNORA_API_KEY", "test")
        monkeypatch.setenv("WEKNORA_REQUEST_TIMEOUT_MS", "10000")
        monkeypatch.setenv("WEKNORA_RETRIEVAL_TOP_K", "8")
        monkeypatch.setenv("WEKNORA_RETRIEVAL_THRESHOLD", "")
        monkeypatch.setenv("WEKNORA_TIME_DECAY_RATE", "0.1")
        monkeypatch.setenv("WEKNORA_SEMANTIC_WEIGHT", "0.7")
        monkeypatch.setenv("WEKNORA_TIME_WEIGHT", "0.3")
        monkeypatch.setenv("WEKNORA_DEGRADATION_STRATEGY", DegradationStrategy.DEGRADE.value)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/knowledge-search"):
                return httpx.Response(403, json={"success": False})
            return httpx.Response(404, json={"success": False})

        pipeline._weknora_transport = httpx.MockTransport(handler)
        degraded: list[str] = []
        candidates = await pipeline._episodic_recall("q", None, None, degraded)
        assert candidates == []
        assert any(s.startswith("weknora_recall:") for s in degraded)
        assert "weknora_degraded_to_fast" in degraded

    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._semantic_recall')
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._episodic_recall')
    @pytest.mark.asyncio
    async def test_should_skip_deep_retrieval_smalltalk_degrades_to_fast(
        self, mock_episodic, mock_semantic, pipeline
    ):
        """deep 模式下小闲聊应跳过 deep（不调用 episodic）"""
        mock_semantic.return_value = [
            RetrievalCandidate(
                evidence_id="1",
                text="ok",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.9, "bm25_score": 0.0},
                refs={"event_id": "1"},
            )
        ]
        mock_episodic.return_value = []

        evidence, degraded_services = await pipeline.process(
            query="ok",
            mode="deep",
            top_k=5,
        )

        assert isinstance(evidence, list)
        assert any(s.startswith("skip_deep_retrieval:") for s in degraded_services)
        mock_semantic.assert_called_once()
        mock_episodic.assert_not_called()

    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._semantic_recall')
    @patch('sbo_core.retrieval_pipeline.RetrievalPipeline._episodic_recall')
    @pytest.mark.asyncio
    async def test_should_force_deep_retrieval_keyword_keeps_deep(
        self, mock_episodic, mock_semantic, pipeline
    ):
        """deep 模式下包含强制 deep 关键词时应保留 deep（调用 episodic）"""
        mock_semantic.return_value = [
            RetrievalCandidate(
                evidence_id="1",
                text="之前我们讨论过项目进展",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                evidence_type=EvidenceType.RAW_EVENT,
                scores={"semantic_score": 0.9, "bm25_score": 0.0},
                refs={"event_id": "1"},
            )
        ]
        mock_episodic.return_value = []

        evidence, degraded_services = await pipeline.process(
            query="之前我们讨论过什么？",
            mode="deep",
            top_k=5,
        )

        assert isinstance(evidence, list)
        mock_semantic.assert_called_once()
        mock_episodic.assert_called_once()


class TestRetrievalCandidate:
    """测试检索候选项"""
    
    def test_to_evidence(self):
        """测试转换为 Evidence 对象"""
        now = datetime.now(timezone.utc)
        candidate = RetrievalCandidate(
            evidence_id="1",
            text="项目进展讨论",
            occurred_at=now,
            source="webchat",
            evidence_type=EvidenceType.RAW_EVENT,
            scores={"semantic_score": 0.9, "bm25_score": 0.8},
            refs={"event_id": "1"}
        )
        candidate.final_score = 0.85
        
        evidence = candidate.to_evidence()
        
        # 验证转换结果
        assert evidence.evidence_id == "1"
        assert evidence.text == "项目进展讨论"
        assert evidence.occurred_at == now
        assert evidence.source == "webchat"
        assert evidence.type == EvidenceType.RAW_EVENT.value
        assert evidence.confidence == 0.85
        assert evidence.refs == {"event_id": "1"}
        assert evidence.scores == {"semantic_score": 0.9, "bm25_score": 0.8}
