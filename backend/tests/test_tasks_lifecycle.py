"""
生命周期/衰减任务单元测试

测试覆盖：
1. 时间衰减计算
2. 重排应用
3. 访问统计更新
4. 阶段 2 接口预留
"""

from __future__ import annotations

import pytest
import math
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

from sbo_core.tasks_lifecycle import (
    LifecycleService,
    AccessTrackingService,
    lifecycle_service,
    access_tracking_service,
    TimeDecayConfig,
)


class TestTimeDecayCalculation:
    """测试时间衰减计算"""
    
    def test_exponential_decay_same_day(self):
        """测试同一天的时间衰减"""
        now = datetime.now(timezone.utc)
        score = lifecycle_service.calculate_time_decay_score(now, now)
        assert score == 1.0  # 同一天应该返回 1.0
    
    def test_exponential_decay_one_day_ago(self):
        """测试一天前的时间衰减"""
        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)
        score = lifecycle_service.calculate_time_decay_score(one_day_ago, now)
        
        expected = math.exp(-0.1 * 1)  # decay_rate=0.1, days_ago=1
        assert abs(score - expected) < 0.001
    
    def test_exponential_decay_ten_days_ago(self):
        """测试十天前的时间衰减"""
        now = datetime.now(timezone.utc)
        ten_days_ago = now - timedelta(days=10)
        score = lifecycle_service.calculate_time_decay_score(ten_days_ago, now)
        
        expected = math.exp(-0.1 * 10)  # decay_rate=0.1, days_ago=10
        assert abs(score - expected) < 0.001
    
    def test_decay_max_days_cap(self):
        """测试最大天数限制"""
        now = datetime.now(timezone.utc)
        very_old = now - timedelta(days=500)  # 超过 max_days=365
        score = lifecycle_service.calculate_time_decay_score(very_old, now)
        
        expected = math.exp(-0.1 * 365)  # 应该按 365 天计算
        assert abs(score - expected) < 0.001
    
    def test_decay_future_date(self):
        """测试未来日期（应该返回 1.0）"""
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=1)
        score = lifecycle_service.calculate_time_decay_score(future, now)
        assert score == 1.0  # 未来日期应该返回 1.0


class TestTimeDecayReranking:
    """测试时间衰减重排"""
    
    def test_time_decay_reranking_basic(self):
        """测试基本时间衰减重排"""
        now = datetime.now(timezone.utc)
        
        candidates = [
            {
                "evidence_id": "ev1",
                "scores": {"fusion_score": 0.9},
                "occurred_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "evidence_id": "ev2",
                "scores": {"fusion_score": 0.8},
                "occurred_at": now.isoformat(),
            },
        ]
        
        results = lifecycle_service.apply_time_decay_reranking(candidates, now)
        
        # ev2 是今天的，应该排在前面（虽然原始分数较低）
        assert results[0].evidence_id == "ev2"
        assert results[1].evidence_id == "ev1"
    
    def test_time_decay_formula(self):
        """测试时间衰减重排公式"""
        now = datetime.now(timezone.utc)
        three_days_ago = now - timedelta(days=3)
        
        candidates = [
            {
                "evidence_id": "ev1",
                "scores": {"fusion_score": 1.0},
                "occurred_at": three_days_ago.isoformat(),
            },
        ]
        
        results = lifecycle_service.apply_time_decay_reranking(candidates, now)
        
        # 公式: final_score = 1.0 * 0.8 + time_score * 0.2
        time_score = math.exp(-0.1 * 3)
        expected = 1.0 * 0.8 + time_score * 0.2
        
        assert abs(results[0].final_score - expected) < 0.001
        assert results[0].days_ago == 3


class TestAccessTracking:
    """测试访问追踪"""
    
    @pytest.mark.asyncio
    async def test_record_access_batch_new_records(self):
        """测试创建新的访问记录"""
        with patch('sbo_core.tasks_lifecycle.get_database') as mock_get_db:
            mock_session = MagicMock()
            mock_db = MagicMock()
            mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_db.return_value = mock_db
            
            # 模拟查询返回 None（新记录）
            mock_session.query.return_value.filter.return_value.first.return_value = None
            
            updated = await access_tracking_service.record_access_batch(
                user_id="user1",
                evidence_ids=["ev1", "ev2"],
            )
            
            assert updated == 2
            assert mock_session.add.call_count == 2
            mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_record_access_batch_update_existing(self):
        """测试更新现有访问记录"""
        with patch('sbo_core.tasks_lifecycle.get_database') as mock_get_db:
            mock_session = MagicMock()
            mock_db = MagicMock()
            mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_db.return_value = mock_db
            
            # 模拟现有记录
            existing_record = MagicMock()
            existing_record.access_count = 5
            existing_record.last_accessed_at = datetime.now(timezone.utc) - timedelta(days=1)
            mock_session.query.return_value.filter.return_value.first.return_value = existing_record
            
            updated = await access_tracking_service.record_access_batch(
                user_id="user1",
                evidence_ids=["ev1"],
            )
            
            assert updated == 1
            assert existing_record.access_count == 6  # 5 + 1
            assert existing_record.last_accessed_at is not None
            mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_record_access_batch_empty_input(self):
        """测试空输入处理"""
        updated = await access_tracking_service.record_access_batch(
            user_id="",
            evidence_ids=[],
        )
        assert updated == 0


class TestStage2Interfaces:
    """测试阶段 2 预留接口"""
    
    def test_reinforcement_score_calculation(self):
        """测试强化衰减分数计算"""
        now = datetime.now(timezone.utc)
        occurred_at = now - timedelta(days=10)
        last_accessed = now - timedelta(days=2)
        
        score = lifecycle_service.calculate_reinforcement_score(
            access_count=10,
            last_accessed_at=last_accessed,
            occurred_at=occurred_at,
            reference_time=now,
        )
        
        # 验证分数在合理范围内
        assert 0 < score <= 1.0
        # 访问次数越多分数应该越高
        assert score > math.exp(-0.1 * 10)  # 应该比基础衰减高
    
    @pytest.mark.asyncio
    async def test_get_access_stats(self):
        """测试获取访问统计"""
        with patch('sbo_core.tasks_lifecycle.get_database') as mock_get_db:
            mock_session = MagicMock()
            mock_db = MagicMock()
            mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_get_db.return_value = mock_db
            
            # 模拟统计记录
            mock_stat = MagicMock()
            mock_stat.access_count = 10
            mock_stat.last_accessed_at = datetime.now(timezone.utc)
            mock_session.query.return_value.filter.return_value.first.return_value = mock_stat
            
            stats = await lifecycle_service.get_access_stats(
                user_id="user1",
                evidence_ids=["ev1", "ev2"],
            )
            
            assert "ev1" in stats
            assert stats["ev1"]["access_count"] == 10
            assert "last_accessed_at" in stats["ev1"]


class TestTimeDecayConfig:
    """测试时间衰减配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = TimeDecayConfig()
        assert config.decay_rate == 0.1
        assert config.semantic_weight == 0.8
        assert config.time_weight == 0.2
        assert config.max_days == 365


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
