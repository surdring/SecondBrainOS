"""
用户档案更新任务单元测试 - 4.5

测试内容：
1. 冲突检测逻辑
2. 版本化机制
3. 历史记录归档

依赖需求：2.2.1, 3.4.1
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest

from sbo_core.tasks_profile import (
    ProfileConflictResolver,
    ProfileVersionManager,
    ProfileChange,
    ConflictCheckResult,
    ConflictResolutionStrategy,
    ProfileUpdateType,
    upsert_profile,
    enqueue_profile_update,
    get_profile_with_history,
)
from sbo_core.errors import ErrorCode, AppError


class TestProfileConflictResolver:
    """档案冲突检测器单元测试"""
    
    @pytest.fixture
    def resolver(self):
        """创建冲突解析器实例"""
        return ProfileConflictResolver()
    
    @pytest.fixture
    def empty_profile(self):
        """创建空档案"""
        return {
            "profile": {
                "facts": {},
                "preferences": {},
                "constraints": {},
            },
            "version": 1,
        }
    
    @pytest.fixture
    def existing_profile(self):
        """创建已有数据的档案"""
        return {
            "profile": {
                "facts": {
                    "name": "张三",
                    "id_card": "110101199001011234",
                },
                "preferences": {
                    "hobby": "篮球",
                    "diet": "普通饮食",
                },
                "constraints": {
                    "allergy": "无",
                },
            },
            "version": 2,
        }
    
    def test_check_conflict_no_existing_value(self, resolver, empty_profile):
        """测试无现有值时的冲突检查（应无冲突）"""
        result = resolver.check_conflict(
            field_type="preferences",
            field_key="hobby",
            new_value="游泳",
            new_confidence=0.8,
            current_profile=empty_profile
        )
        
        assert result.has_conflict is False
        assert result.new_value == "游泳"
        assert result.suggested_strategy == ConflictResolutionStrategy.OVERWRITE
    
    def test_check_conflict_same_value(self, resolver, existing_profile):
        """测试相同值时的冲突检查（应无冲突）"""
        result = resolver.check_conflict(
            field_type="preferences",
            field_key="hobby",
            new_value="篮球",  # 与现有值相同
            new_confidence=0.8,
            current_profile=existing_profile
        )
        
        assert result.has_conflict is False
        assert result.existing_value == "篮球"
    
    def test_check_conflict_different_value_preference(self, resolver, existing_profile):
        """测试偏好变更时的冲突检测"""
        result = resolver.check_conflict(
            field_type="preferences",
            field_key="hobby",
            new_value="足球",  # 与现有值不同
            new_confidence=0.8,
            current_profile=existing_profile
        )
        
        assert result.has_conflict is True
        assert result.existing_value == "篮球"
        assert result.new_value == "足球"
        # 偏好变更应建议使用版本化策略
        assert result.suggested_strategy == ConflictResolutionStrategy.VERSION
    
    def test_check_conflict_stable_fact_high_confidence(self, resolver, existing_profile):
        """测试高置信度稳定事实变更"""
        result = resolver.check_conflict(
            field_type="facts",
            field_key="id_card",
            new_value="110101199001015678",  # 与现有值不同
            new_confidence=0.9,  # 高置信度
            current_profile=existing_profile
        )
        
        assert result.has_conflict is True
        # 稳定事实高置信度时应使用版本化
        assert result.suggested_strategy == ConflictResolutionStrategy.VERSION
    
    def test_check_conflict_stable_fact_low_confidence(self, resolver, existing_profile):
        """测试低置信度稳定事实变更"""
        result = resolver.check_conflict(
            field_type="facts",
            field_key="id_card",
            new_value="110101199001015678",
            new_confidence=0.4,  # 低置信度
            current_profile=existing_profile
        )
        
        assert result.has_conflict is True
        # 低置信度稳定事实应建议拒绝
        assert result.suggested_strategy == ConflictResolutionStrategy.REJECT
    
    def test_check_conflict_constraint_field(self, resolver, existing_profile):
        """测试约束字段冲突检测"""
        result = resolver.check_conflict(
            field_type="constraints",
            field_key="allergy",
            new_value="青霉素过敏",
            new_confidence=0.7,
            current_profile=existing_profile
        )
        
        assert result.has_conflict is True
        # 约束字段应使用版本化
        assert result.suggested_strategy == ConflictResolutionStrategy.VERSION
    
    def test_resolve_conflict_overwrite(self, resolver):
        """测试覆写策略"""
        conflict = ConflictCheckResult(
            has_conflict=True,
            existing_value="旧值",
            new_value="新值",
            field_type="preferences",
            field_key="test",
        )
        
        final_value, strategy, reason = resolver.resolve_conflict(
            conflict, ConflictResolutionStrategy.OVERWRITE
        )
        
        assert final_value == "新值"
        assert strategy == ConflictResolutionStrategy.OVERWRITE
    
    def test_resolve_conflict_version(self, resolver):
        """测试版本化策略"""
        conflict = ConflictCheckResult(
            has_conflict=True,
            existing_value="旧值",
            new_value="新值",
            field_type="preferences",
            field_key="test",
        )
        
        final_value, strategy, reason = resolver.resolve_conflict(
            conflict, ConflictResolutionStrategy.VERSION
        )
        
        assert final_value == "新值"
        assert strategy == ConflictResolutionStrategy.VERSION
        assert "Versioned" in reason or "versioned" in reason.lower()
    
    def test_resolve_conflict_reject(self, resolver):
        """测试拒绝策略"""
        conflict = ConflictCheckResult(
            has_conflict=True,
            existing_value="旧值",
            new_value="新值",
            field_type="facts",
            field_key="id_card",
        )
        
        final_value, strategy, reason = resolver.resolve_conflict(
            conflict, ConflictResolutionStrategy.REJECT
        )
        
        assert final_value == "旧值"  # 保留旧值
        assert strategy == ConflictResolutionStrategy.REJECT
    
    def test_resolve_conflict_no_conflict(self, resolver):
        """测试无冲突情况"""
        conflict = ConflictCheckResult(
            has_conflict=False,
            new_value="新值",
            field_type="preferences",
            field_key="test",
        )
        
        final_value, strategy, reason = resolver.resolve_conflict(conflict)
        
        assert final_value == "新值"
        assert strategy == ConflictResolutionStrategy.OVERWRITE
        assert "No conflict" in reason
    
    def test_try_merge_values_list(self, resolver):
        """测试列表合并"""
        old = ["a", "b"]
        new = ["b", "c"]
        
        merged = resolver._try_merge_values(old, new)
        
        assert "a" in merged
        assert "b" in merged
        assert "c" in merged
    
    def test_try_merge_values_dict(self, resolver):
        """测试字典合并"""
        old = {"key1": "value1", "nested": {"a": 1}}
        new = {"key2": "value2", "nested": {"b": 2}}
        
        merged = resolver._try_merge_values(old, new)
        
        assert merged["key1"] == "value1"
        assert merged["key2"] == "value2"
        assert merged["nested"]["a"] == 1
        assert merged["nested"]["b"] == 2


class TestProfileVersionManager:
    """档案版本管理器单元测试"""
    
    @pytest.fixture
    def version_manager(self):
        """创建版本管理器实例"""
        return ProfileVersionManager()
    
    @pytest.fixture
    def mock_session(self):
        """创建模拟数据库会话"""
        return MagicMock()
    
    def test_archive_current_version(self, version_manager, mock_session):
        """测试当前版本归档"""
        user_id = "test_user"
        current_profile = {
            "user_id": user_id,
            "profile": {"facts": {"name": "张三"}},
            "version": 3,
        }
        reason = "Preference change from coffee to tea"
        extraction_id = str(uuid.uuid4())
        
        version_id = version_manager.archive_current_version(
            mock_session,
            user_id,
            current_profile,
            reason,
            extraction_id
        )
        
        # 验证版本ID被生成
        assert isinstance(version_id, uuid.UUID)
        
        # 验证执行了插入语句
        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        
        # 验证SQL包含关键字段
        sql = call_args[0][0].text if hasattr(call_args[0][0], 'text') else str(call_args[0][0])
        assert "user_profile_versions" in sql
    
    def test_get_profile_history(self, version_manager, mock_session):
        """测试获取档案历史"""
        user_id = "test_user"
        
        # 设置模拟返回数据
        mock_result = [
            (
                uuid.uuid4(),
                3,
                {"facts": {"name": "张三"}},
                "Initial creation",
                None,
                datetime.now(timezone.utc),
            ),
            (
                uuid.uuid4(),
                2,
                {"facts": {"name": "张三"}},
                "Preference update",
                uuid.uuid4(),
                datetime.now(timezone.utc),
            ),
        ]
        mock_session.execute.return_value = mock_result
        
        history = version_manager.get_profile_history(mock_session, user_id, limit=10)
        
        # 验证返回历史记录
        assert len(history) == 2
        assert history[0]["version"] == 3
        assert history[1]["version"] == 2
        assert "profile" in history[0]
        assert "reason" in history[0]


class TestUpsertProfileTask:
    """档案更新任务单元测试"""
    
    @pytest.fixture
    def mock_database(self):
        """创建模拟数据库"""
        with patch("sbo_core.tasks_profile.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_session = MagicMock()
            mock_db.get_session.return_value = mock_session
            mock_get_db.return_value = mock_db
            
            # 设置 session 的上下文管理器行为
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            
            yield mock_db, mock_session
    
    def test_upsert_profile_preference_update(self, mock_database):
        """测试偏好更新"""
        mock_db, mock_session = mock_database
        
        extraction_id = str(uuid.uuid4())
        user_id = "test_user"
        
        # 设置模拟提取数据
        mock_session.execute.return_value.first.return_value = (
            uuid.uuid4(),  # event_id
            "preference",  # extraction_type
            {
                "category": "hobby",
                "old_value": None,
                "new_value": "游泳",
                "is_constraint": False,
            },  # content
            0.8,  # confidence
            user_id,  # user_id
            "我喜欢游泳",  # event_content
        )
        
        # 设置当前档案查询返回
        mock_session.execute.return_value.first.side_effect = [
            (
                uuid.uuid4(),  # event_id
                "preference",
                {"category": "hobby", "new_value": "游泳", "is_constraint": False},
                0.8,
                user_id,
                "我喜欢游泳",
            ),
            None,  # 无现有档案
        ]
        
        with patch("sbo_core.tasks_profile.audit_log"):
            result = upsert_profile(extraction_id, user_id)
        
        # 验证结果
        assert result["user_id"] == user_id
        assert result["extraction_id"] == extraction_id
        assert result["status"] == "succeeded"
        assert result["version"] == 1  # 新档案，版本从0+1开始
    
    def test_upsert_profile_extraction_not_found(self, mock_database):
        """测试提取不存在时的处理"""
        mock_db, mock_session = mock_database
        
        extraction_id = str(uuid.uuid4())
        
        # 设置提取不存在
        mock_session.execute.return_value.first.return_value = None
        
        with pytest.raises(AppError) as exc_info:
            upsert_profile(extraction_id)
        
        assert exc_info.value.code == ErrorCode.EXTRACTION_NOT_FOUND
    
    def test_upsert_profile_invalid_uuid(self):
        """测试无效 UUID 的处理"""
        with pytest.raises(AppError) as exc_info:
            upsert_profile("invalid-uuid-format")
        
        assert exc_info.value.code == ErrorCode.PROFILE_UPDATE_FAILED
        assert "Invalid extraction_id format" in exc_info.value.message
    
    def test_upsert_profile_conflict_resolution_versioning(self, mock_database):
        """测试冲突解决和版本化"""
        mock_db, mock_session = mock_database
        
        extraction_id = str(uuid.uuid4())
        user_id = "test_user"
        
        # 设置提取数据（偏好变化）
        mock_session.execute.return_value.first.side_effect = [
            (
                uuid.uuid4(),
                "preference",
                {"category": "hobby", "new_value": "足球", "is_constraint": False},
                0.9,
                user_id,
                "我现在喜欢足球",
            ),
            # 现有档案（有旧偏好）
            (
                user_id,
                {"facts": {}, "preferences": {"hobby": "篮球"}, "constraints": {}},
                2,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            ),
        ]
        
        with patch("sbo_core.tasks_profile.audit_log"):
            with patch.object(ProfileVersionManager, "archive_current_version") as mock_archive:
                result = upsert_profile(extraction_id, user_id)
        
        # 验证版本号递增
        assert result["version"] == 3
        # 验证有变更记录
        assert result["changes_count"] >= 1
        # 验证版本化被触发（因为有冲突）
        mock_archive.assert_called_once()
    
    def test_upsert_profile_constraint_update(self, mock_database):
        """测试约束/禁忌更新"""
        mock_db, mock_session = mock_database
        
        extraction_id = str(uuid.uuid4())
        user_id = "test_user"
        
        # 设置提取数据（新的饮食禁忌）
        mock_session.execute.return_value.first.side_effect = [
            (
                uuid.uuid4(),
                "preference",
                {"category": "dietary_constraint", "new_value": "不吃海鲜", "is_constraint": True},
                0.85,
                user_id,
                "医生让我忌口海鲜",
            ),
            None,  # 无现有档案
        ]
        
        with patch("sbo_core.tasks_profile.audit_log"):
            result = upsert_profile(extraction_id, user_id)
        
        assert result["status"] == "succeeded"
        assert result["changes_count"] >= 1


class TestProfileVersioningIntegration:
    """档案版本化集成测试"""
    
    def test_full_conflict_resolution_flow(self):
        """测试完整冲突解决流程"""
        resolver = ProfileConflictResolver()
        
        # 初始档案
        current_profile = {
            "profile": {
                "preferences": {"hobby": "篮球", "diet": "普通"},
                "facts": {"name": "张三"},
                "constraints": {},
            },
            "version": 1,
        }
        
        # 场景1: 偏好变更（有冲突）
        conflict = resolver.check_conflict(
            field_type="preferences",
            field_key="hobby",
            new_value="足球",
            new_confidence=0.8,
            current_profile=current_profile
        )
        
        assert conflict.has_conflict is True
        assert conflict.existing_value == "篮球"
        
        # 解决冲突
        final_value, strategy, reason = resolver.resolve_conflict(conflict)
        
        assert final_value == "足球"
        assert strategy == ConflictResolutionStrategy.VERSION
        
        # 场景2: 新偏好（无冲突）
        conflict2 = resolver.check_conflict(
            field_type="preferences",
            field_key="music",
            new_value="摇滚",
            new_confidence=0.7,
            current_profile=current_profile
        )
        
        assert conflict2.has_conflict is False


class TestProfileTaskRetry:
    """档案任务重试机制单元测试"""
    
    def test_task_wrapper_configuration(self):
        """测试任务包装器配置"""
        from sbo_core.tasks_profile import upsert_profile
        
        # 验证任务有正确的配置
        assert hasattr(upsert_profile, "_task_config")
        config = upsert_profile._task_config
        assert config["max_retries"] == 3
        assert config["timeout"] == 300


class TestProfileEnqueueAndQuery:
    """档案任务入队和查询单元测试"""
    
    @patch("sbo_core.tasks_profile.enqueue_task")
    def test_enqueue_profile_update(self, mock_enqueue_task):
        """测试档案更新任务入队"""
        extraction_id = uuid.uuid4()
        user_id = "test_user"
        
        enqueue_profile_update(extraction_id, user_id)
        
        # 验证 enqueue_task 被调用
        mock_enqueue_task.assert_called_once()
        call_args = mock_enqueue_task.call_args
        
        # 验证参数
        assert call_args[1]["queue_name"] == "sbo_default"
        assert call_args[1]["timeout"] == 300
    
    @patch("sbo_core.tasks_profile.get_database")
    def test_get_profile_with_history(self, mock_get_db):
        """测试获取档案及历史"""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        # 设置模拟返回数据
        mock_session.execute.return_value.first.return_value = (
            "test_user",
            {"facts": {"name": "张三"}},
            5,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )
        
        user_id = "test_user"
        
        with patch.object(ProfileVersionManager, "get_profile_history") as mock_history:
            mock_history.return_value = [
                {"version": 4, "reason": "Preference change"},
                {"version": 3, "reason": "Fact update"},
            ]
            
            result = get_profile_with_history(user_id, include_history=True, history_limit=10)
        
        # 验证返回结果包含历史
        assert result["exists"] is True
        assert result["version"] == 5
        assert "history" in result
        assert len(result["history"]) == 2
    
    @patch("sbo_core.tasks_profile.get_database")
    def test_get_profile_not_found(self, mock_get_db):
        """测试获取不存在的档案"""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        # 设置档案不存在
        mock_session.execute.return_value.first.return_value = None
        
        user_id = "non_existent_user"
        result = get_profile_with_history(user_id)
        
        # 验证返回空档案结构
        assert result["exists"] is False
        assert result["version"] == 0
        assert "facts" in result["profile"]
        assert "preferences" in result["profile"]
        assert "constraints" in result["profile"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
