"""
Cross-Encoder 重排任务单元测试

测试覆盖：
1. 重排任务执行
2. 降级策略
3. 混合评分
4. 符号查询保护
5. 并发控制
"""

from __future__ import annotations

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from sbo_core.tasks_rerank import (
    RerankTaskService,
    RerankCandidate,
    HybridScoreConfig,
    rerank_service,
)
from sbo_core.rerank_client import RerankResult
from sbo_core.errors import AppError, ErrorCode


class TestRerankTaskService:
    """测试重排任务服务"""
    
    @pytest.fixture
    def sample_candidates(self):
        """样本候选数据"""
        return [
            {
                "evidence_id": "ev1",
                "text": "This is a test document about AI",
                "source": "weknora",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "scores": {"semantic_score": 0.8, "bm25_score": 0.6, "fusion_score": 0.75},
            },
            {
                "evidence_id": "ev2",
                "text": "Another document about machine learning",
                "source": "weknora",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "scores": {"semantic_score": 0.7, "bm25_score": 0.5, "fusion_score": 0.65},
            },
            {
                "evidence_id": "ev3",
                "text": "CONFIG_VAR=value environment setting",
                "source": "weknora",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "scores": {"semantic_score": 0.5, "bm25_score": 0.9, "fusion_score": 0.55},
            },
        ]
    
    @pytest.fixture
    def mock_rerank_results(self):
        """模拟重排结果"""
        return [
            RerankResult(evidence_id="ev1", score=0.85),
            RerankResult(evidence_id="ev2", score=0.75),
            RerankResult(evidence_id="ev3", score=0.60),
        ]
    
    @pytest.mark.asyncio
    async def test_rerank_not_configured(self, sample_candidates):
        """测试未配置重排服务时返回原始候选"""
        with patch('sbo_core.tasks_rerank.load_settings') as mock_settings:
            mock_settings.return_value = MagicMock(rerank_provider_url="")
            
            result = await rerank_service.execute_rerank_task(
                query="test query",
                candidates=sample_candidates,
                is_symbolic=False,
            )
            
            assert result.rerank_applied is False
            assert result.fallback_reason == "rerank_not_configured"
            assert len(result.candidates) == len(sample_candidates)
    
    @pytest.mark.asyncio
    async def test_rerank_success(self, sample_candidates, mock_rerank_results):
        """测试重排成功"""
        with patch('sbo_core.tasks_rerank.load_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                rerank_provider_url="http://test.com",
                rerank_api_key="test_key",
                rerank_timeout_ms=1000,
                rerank_max_candidates=20,
                rerank_weight=0.5,
                rerank_model_id="test_model",
            )
            
            with patch('sbo_core.tasks_rerank.RerankClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.rerank = AsyncMock(return_value=mock_rerank_results)
                MockClient.return_value = mock_client
                
                result = await rerank_service.execute_rerank_task(
                    query="test query",
                    candidates=sample_candidates,
                    is_symbolic=False,
                )
                
                assert result.rerank_applied is True
                assert result.fallback_reason is None
                assert result.provider_used == "http://test.com"
                assert result.model_used == "test_model"
    
    @pytest.mark.asyncio
    async def test_rerank_timeout_fallback(self, sample_candidates):
        """测试超时降级"""
        with patch('sbo_core.tasks_rerank.load_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                rerank_provider_url="http://test.com",
                rerank_api_key="test_key",
                rerank_timeout_ms=1000,
                rerank_max_candidates=20,
                rerank_weight=0.5,
            )
            
            with patch('sbo_core.tasks_rerank.RerankClient') as MockClient:
                mock_client = AsyncMock()
                # 模拟超时错误
                error = AppError(
                    code=ErrorCode.RERANK_FAILED,
                    message="Rerank provider timeout",
                    status_code=503,
                )
                mock_client.rerank = AsyncMock(side_effect=error)
                MockClient.return_value = mock_client
                
                result = await rerank_service.execute_rerank_task(
                    query="test query",
                    candidates=sample_candidates,
                    is_symbolic=False,
                )
                
                assert result.rerank_applied is False
                assert result.fallback_reason == "timeout"
                assert len(result.candidates) == len(sample_candidates)
    
    @pytest.mark.asyncio
    async def test_rerank_5xx_fallback(self, sample_candidates):
        """测试 5xx 错误降级"""
        with patch('sbo_core.tasks_rerank.load_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                rerank_provider_url="http://test.com",
                rerank_api_key="test_key",
                rerank_timeout_ms=1000,
                rerank_max_candidates=20,
                rerank_weight=0.5,
            )
            
            with patch('sbo_core.tasks_rerank.RerankClient') as MockClient:
                mock_client = AsyncMock()
                error = AppError(
                    code=ErrorCode.RERANK_FAILED,
                    message="Rerank provider returned server error",
                    status_code=503,
                    details={"status_code": 500},
                )
                mock_client.rerank = AsyncMock(side_effect=error)
                MockClient.return_value = mock_client
                
                result = await rerank_service.execute_rerank_task(
                    query="test query",
                    candidates=sample_candidates,
                    is_symbolic=False,
                )
                
                assert result.rerank_applied is False
                assert result.fallback_reason == "5xx"


class TestHybridScoring:
    """测试混合评分"""
    
    def test_hybrid_scoring_formula(self):
        """测试混合评分公式"""
        candidates = [
            RerankCandidate(
                evidence_id="ev1",
                text="Test",
                source="test",
                occurred_at=datetime.now(timezone.utc),
                scores={"fusion_score": 0.8},
                original_rank=0,
            ),
        ]
        
        rerank_results = [RerankResult(evidence_id="ev1", score=0.9)]
        
        result = rerank_service._apply_hybrid_scoring(
            candidates=candidates,
            rerank_results=rerank_results,
            is_symbolic=False,
            rerank_weight=0.5,
        )
        
        # 混合公式：final_score = 0.5 * 0.8 + 0.5 * 0.9 = 0.85
        # 验证分数在合理范围内（浮点数精度问题）
        assert abs(result[0].scores["final_score"] - 0.85) < 0.001
        assert result[0].scores["rerank_score"] == 0.9
        assert result[0].scores["fusion_score"] == 0.8
    
    def test_symbolic_query_preservation(self):
        """测试符号查询保底保护"""
        candidates = [
            RerankCandidate(
                evidence_id="ev1",
                text="ENV_VAR=test_value",
                source="test",
                occurred_at=datetime.now(timezone.utc),
                scores={
                    "fusion_score": 0.3,  # 低融合分数
                    "bm25_score": 0.9,     # 但高 BM25 分数
                    "lexical_score": 0.9,
                },
                original_rank=0,
            ),
        ]
        
        rerank_results = [RerankResult(evidence_id="ev1", score=0.2)]  # 低重排分数
        
        result = rerank_service._apply_hybrid_scoring(
            candidates=candidates,
            rerank_results=rerank_results,
            is_symbolic=True,  # 符号查询
            rerank_weight=0.5,
        )
        
        # 符号查询保护应该生效，保底阈值 0.35
        assert result[0].scores["preservation_floor_applied"] == 1.0
        assert result[0].scores["final_score"] >= 0.35


class TestFallbackReasonClassification:
    """测试降级原因分类"""
    
    def test_timeout_classification(self):
        """测试超时分类"""
        error = AppError(
            code=ErrorCode.RERANK_FAILED,
            message="Rerank provider timeout",
            status_code=503,
        )
        reason = rerank_service._classify_fallback_reason(error)
        assert reason == "timeout"
    
    def test_5xx_classification(self):
        """测试 5xx 分类"""
        error = AppError(
            code=ErrorCode.RERANK_FAILED,
            message="Server error occurred",
            status_code=503,
            details={"status_code": 502},
        )
        reason = rerank_service._classify_fallback_reason(error)
        assert reason == "5xx"
    
    def test_auth_failure_classification(self):
        """测试认证失败分类"""
        error = AppError(
            code=ErrorCode.RERANK_FAILED,
            message="Rerank provider auth failed",
            status_code=503,
        )
        reason = rerank_service._classify_fallback_reason(error)
        assert reason == "auth_failed"


class TestConcurrencyControl:
    """测试并发控制"""
    
    def test_semaphore_initialization(self):
        """测试信号量初始化"""
        service = RerankTaskService()
        semaphore = service._get_semaphore()
        assert semaphore._value == 5  # 默认 5 个并发


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
