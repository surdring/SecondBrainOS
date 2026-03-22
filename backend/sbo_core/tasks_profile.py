"""
用户档案更新任务实现 - 4.4

功能：
1. 实现 upsert_profile(extraction_id) 任务
2. 实现记忆冲突检测和解决
3. 实现档案版本化管理

依赖需求：2.2.1, 3.4.1
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sbo_core.tasks_framework import (
    task_wrapper, enqueue_task, QUEUE_DEFAULT, TaskPriority, TaskStatus,
    update_consolidation_job_status
)
from sbo_core.audit import audit_log
from sbo_core.database import get_database
from sbo_core.config import load_settings
from sbo_core.errors import ErrorCode, AppError


_logger = logging.getLogger("sbo_core.profile_tasks")


class ConflictResolutionStrategy(str, Enum):
    """冲突解决策略"""
    OVERWRITE = "overwrite"           # 直接覆写
    VERSION = "version"               # 版本化（保留历史）
    MERGE = "merge"                   # 合并
    REJECT = "reject"                 # 拒绝（保留旧值）


class ProfileUpdateType(str, Enum):
    """档案更新类型"""
    FACT = "fact"                     # 事实更新
    PREFERENCE = "preference"         # 偏好更新
    CONSTRAINT = "constraint"         # 约束/禁忌更新
    CORRECTION = "correction"         # 纠正


@dataclass
class ProfileChange:
    """档案变更记录"""
    field_type: str                   # facts / preferences / constraints
    field_key: str                    # 字段键
    old_value: Any
    new_value: Any
    confidence: float
    source_extraction_id: str | None
    update_type: ProfileUpdateType
    resolution_strategy: ConflictResolutionStrategy
    reason: str = ""                  # 变更原因


@dataclass
class ConflictCheckResult:
    """冲突检查结果"""
    has_conflict: bool
    existing_value: Any = None
    new_value: Any = None
    field_type: str = ""              # facts / preferences / constraints
    field_key: str = ""
    confidence_existing: float = 0.0
    confidence_new: float = 0.0
    suggested_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.VERSION


class ProfileConflictResolver:
    """档案冲突检测与解决器"""
    
    def __init__(self):
        self._init_conflict_rules()
    
    def _init_conflict_rules(self):
        """初始化冲突检测规则"""
        # 稳定事实字段（不应轻易改变）
        self.stable_fact_fields = [
            "id_card", "passport", "birth_date", "name", "nationality"
        ]
        
        # 可变偏好字段
        self.variable_preference_fields = [
            "hobby", "diet", "work_style", "sleep_time", "exercise"
        ]
        
        # 约束/禁忌字段
        self.constraint_fields = [
            "dietary_constraint", "allergy", "medical_constraint", "time_constraint"
        ]
        
        # 高置信度阈值
        self.high_confidence_threshold = 0.8
        
        # 低置信度阈值（低于此值视为不确定）
        self.low_confidence_threshold = 0.5
    
    def check_conflict(
        self,
        field_type: str,
        field_key: str,
        new_value: Any,
        new_confidence: float,
        current_profile: dict[str, Any]
    ) -> ConflictCheckResult:
        """检查是否存在冲突
        
        Args:
            field_type: 字段类型 (facts/preferences/constraints)
            field_key: 字段键
            new_value: 新值
            new_confidence: 新值置信度
            current_profile: 当前档案
            
        Returns:
            冲突检查结果
        """
        profile_data = current_profile.get("profile", current_profile)
        existing_value = None
        
        # 获取现有值
        if field_type in profile_data:
            existing_value = profile_data[field_type].get(field_key)
        
        # 如果没有现有值，不存在冲突
        if existing_value is None:
            return ConflictCheckResult(
                has_conflict=False,
                new_value=new_value,
                field_type=field_type,
                field_key=field_key,
                confidence_new=new_confidence,
                suggested_strategy=ConflictResolutionStrategy.OVERWRITE
            )
        
        # 如果值相同，不存在冲突
        if existing_value == new_value:
            return ConflictCheckResult(
                has_conflict=False,
                existing_value=existing_value,
                new_value=new_value,
                field_type=field_type,
                field_key=field_key,
                confidence_existing=0.0,  # 未知
                confidence_new=new_confidence,
                suggested_strategy=ConflictResolutionStrategy.OVERWRITE
            )
        
        # 存在冲突，确定解决策略
        suggested_strategy = self._determine_resolution_strategy(
            field_type, field_key, new_confidence
        )
        
        return ConflictCheckResult(
            has_conflict=True,
            existing_value=existing_value,
            new_value=new_value,
            field_type=field_type,
            field_key=field_key,
            confidence_existing=0.0,  # 需要查询历史获取
            confidence_new=new_confidence,
            suggested_strategy=suggested_strategy
        )
    
    def _determine_resolution_strategy(
        self,
        field_type: str,
        field_key: str,
        new_confidence: float
    ) -> ConflictResolutionStrategy:
        """确定冲突解决策略"""
        # 对于约束/禁忌字段，总是使用版本化
        if field_type == "constraints" or field_key in self.constraint_fields:
            return ConflictResolutionStrategy.VERSION
        
        # 对于高置信度的稳定事实，使用版本化
        if field_key in self.stable_fact_fields:
            if new_confidence >= self.high_confidence_threshold:
                return ConflictResolutionStrategy.VERSION
            else:
                return ConflictResolutionStrategy.REJECT
        
        # 对于可变偏好，低置信度时拒绝，高置信度时版本化
        if field_key in self.variable_preference_fields:
            if new_confidence >= self.low_confidence_threshold:
                return ConflictResolutionStrategy.VERSION
            else:
                return ConflictResolutionStrategy.REJECT
        
        # 默认策略：版本化
        return ConflictResolutionStrategy.VERSION
    
    def resolve_conflict(
        self,
        conflict: ConflictCheckResult,
        strategy: ConflictResolutionStrategy | None = None
    ) -> tuple[Any, ConflictResolutionStrategy, str]:
        """解决冲突
        
        Args:
            conflict: 冲突检查结果
            strategy: 解决策略（如果为None，使用建议的策略）
            
        Returns:
            (最终值, 使用的策略, 原因)
        """
        if not conflict.has_conflict:
            return conflict.new_value, ConflictResolutionStrategy.OVERWRITE, "No conflict"
        
        actual_strategy = strategy or conflict.suggested_strategy
        
        if actual_strategy == ConflictResolutionStrategy.OVERWRITE:
            return conflict.new_value, actual_strategy, "Direct overwrite"
        
        elif actual_strategy == ConflictResolutionStrategy.VERSION:
            # 版本化：接受新值，但旧值会被归档
            return conflict.new_value, actual_strategy, "Versioned update, old value archived"
        
        elif actual_strategy == ConflictResolutionStrategy.REJECT:
            # 拒绝：保留旧值
            return conflict.existing_value, actual_strategy, "Rejected: existing value has higher priority"
        
        elif actual_strategy == ConflictResolutionStrategy.MERGE:
            # 合并：尝试合并新旧值
            merged = self._try_merge_values(conflict.existing_value, conflict.new_value)
            return merged, actual_strategy, "Merged values"
        
        return conflict.new_value, actual_strategy, "Unknown strategy, defaulting to overwrite"
    
    def _try_merge_values(self, old_value: Any, new_value: Any) -> Any:
        """尝试合并两个值"""
        # 简单合并策略：如果是列表，合并去重
        if isinstance(old_value, list) and isinstance(new_value, list):
            merged = list(old_value)
            for item in new_value:
                if item not in merged:
                    merged.append(item)
            return merged
        
        # 如果是字典，递归合并
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            merged = dict(old_value)
            for key, val in new_value.items():
                if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
                    merged[key] = self._try_merge_values(merged[key], val)
                else:
                    merged[key] = val
            return merged
        
        # 默认：返回新值
        return new_value


class ProfileVersionManager:
    """档案版本管理器"""
    
    def __init__(self):
        pass
    
    def archive_current_version(
        self,
        session,
        user_id: str,
        current_profile: dict[str, Any],
        reason: str,
        source_extraction_id: str | None = None
    ) -> uuid.UUID:
        """归档当前版本
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            current_profile: 当前档案数据
            reason: 归档原因
            source_extraction_id: 来源提取ID
            
        Returns:
            版本记录ID
        """
        from sqlalchemy import text
        
        version_id = uuid.uuid4()
        profile_data = current_profile.get("profile", current_profile)
        version = current_profile.get("version", 1)
        
        session.execute(
            text("""
                INSERT INTO user_profile_versions (
                    profile_version_id, user_id, version, profile, reason, source_extraction_id, created_at
                ) VALUES (
                    :version_id, :user_id, :version, :profile, :reason, :source_extraction_id, NOW()
                )
            """),
            {
                "version_id": version_id,
                "user_id": user_id,
                "version": version,
                "profile": profile_data,
                "reason": reason,
                "source_extraction_id": uuid.UUID(source_extraction_id) if source_extraction_id else None,
            }
        )
        
        _logger.info(f"Archived profile version {version} for user {user_id}")
        
        return version_id
    
    def get_profile_history(
        self,
        session,
        user_id: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取档案历史版本
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            历史版本列表
        """
        from sqlalchemy import text
        
        result = session.execute(
            text("""
                SELECT profile_version_id, version, profile, reason, source_extraction_id, created_at
                FROM user_profile_versions
                WHERE user_id = :user_id
                ORDER BY version DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit}
        )
        
        history = []
        for row in result:
            history.append({
                "version_id": str(row[0]),
                "version": row[1],
                "profile": row[2],
                "reason": row[3],
                "source_extraction_id": str(row[4]) if row[4] else None,
                "created_at": row[5].isoformat() if row[5] else None,
            })
        
        return history


@task_wrapper(max_retries=3, timeout=300)
def upsert_profile(
    extraction_id: str,
    user_id: str | None = None,
    job_id: str | None = None
) -> dict[str, Any]:
    """用户档案更新任务 - 冲突检测 + 版本化
    
    Args:
        extraction_id: 提取ID（字符串格式UUID）
        user_id: 用户ID（可选，如果不提供则从extraction获取）
        job_id: 任务ID（可选）
        
    Returns:
        任务执行结果
        
    Raises:
        AppError: 当任务执行失败时
    """
    _logger.info(f"Starting upsert_profile for extraction_id={extraction_id}, user_id={user_id}")
    
    try:
        extraction_uuid = uuid.UUID(extraction_id)
    except ValueError as e:
        raise AppError(
            code=ErrorCode.PROFILE_UPDATE_FAILED,
            message=f"Invalid extraction_id format: {extraction_id}",
            status_code=400
        ) from e
    
    # 更新任务状态
    if job_id:
        update_consolidation_job_status(job_id, TaskStatus.RUNNING)
    
    try:
        db = get_database()
        session = db.get_session()
        
        try:
            # 1. 获取提取数据
            from sqlalchemy import text
            
            result = session.execute(
                text("""
                    SELECT e.event_id, e.extraction_type, e.content, e.confidence,
                           re.user_id, re.content as event_content
                    FROM extractions e
                    JOIN raw_events re ON e.event_id = re.event_id
                    WHERE e.extraction_id = :extraction_id
                """),
                {"extraction_id": extraction_uuid}
            ).first()
            
            if not result:
                raise AppError(
                    code=ErrorCode.EXTRACTION_NOT_FOUND,
                    message=f"Extraction not found: {extraction_id}",
                    status_code=404
                )
            
            event_id, extraction_type, content, confidence, event_user_id, event_content = result
            
            # 确定用户ID
            target_user_id = user_id or event_user_id
            if not target_user_id:
                # 使用默认用户ID
                target_user_id = "default_user"
            
            # 2. 获取或创建当前档案
            profile_result = session.execute(
                text("""
                    SELECT user_id, profile, version, updated_at
                    FROM user_profiles
                    WHERE user_id = :user_id
                """),
                {"user_id": target_user_id}
            ).first()
            
            if profile_result:
                current_profile = {
                    "user_id": profile_result[0],
                    "profile": profile_result[1],
                    "version": profile_result[2],
                    "updated_at": profile_result[3],
                }
                profile_data = dict(profile_result[1])
            else:
                # 创建新档案
                current_profile = {
                    "user_id": target_user_id,
                    "profile": {"facts": {}, "preferences": {}, "constraints": {}},
                    "version": 0,
                    "updated_at": None,
                }
                profile_data = {"facts": {}, "preferences": {}, "constraints": {}}
            
            # 3. 解析提取内容
            resolver = ProfileConflictResolver()
            version_manager = ProfileVersionManager()
            
            changes: list[ProfileChange] = []
            
            # 根据提取类型处理
            if extraction_type == "preference":
                # 偏好更新
                category = content.get("category", "general")
                new_value = content.get("new_value", "")
                is_constraint = content.get("is_constraint", False)
                
                field_type = "constraints" if is_constraint else "preferences"
                
                conflict = resolver.check_conflict(
                    field_type=field_type,
                    field_key=category,
                    new_value=new_value,
                    new_confidence=confidence,
                    current_profile=current_profile
                )
                
                final_value, strategy, reason = resolver.resolve_conflict(conflict)
                
                changes.append(ProfileChange(
                    field_type=field_type,
                    field_key=category,
                    old_value=conflict.existing_value,
                    new_value=final_value,
                    confidence=confidence,
                    source_extraction_id=extraction_id,
                    update_type=ProfileUpdateType.CONSTRAINT if is_constraint else ProfileUpdateType.PREFERENCE,
                    resolution_strategy=strategy,
                    reason=reason
                ))
                
                # 应用变更
                if strategy != ConflictResolutionStrategy.REJECT:
                    profile_data[field_type][category] = final_value
                    
                    # 如果需要版本化，先归档
                    if strategy == ConflictResolutionStrategy.VERSION and conflict.has_conflict:
                        version_manager.archive_current_version(
                            session,
                            target_user_id,
                            current_profile,
                            f"Conflict resolution: {category} changed from '{conflict.existing_value}' to '{final_value}'",
                            extraction_id
                        )
            
            elif extraction_type == "fact":
                # 事实更新
                key = content.get("key", "unknown")
                new_value = content.get("value", "")
                is_stable = content.get("is_stable", True)
                
                conflict = resolver.check_conflict(
                    field_type="facts",
                    field_key=key,
                    new_value=new_value,
                    new_confidence=confidence,
                    current_profile=current_profile
                )
                
                final_value, strategy, reason = resolver.resolve_conflict(conflict)
                
                changes.append(ProfileChange(
                    field_type="facts",
                    field_key=key,
                    old_value=conflict.existing_value,
                    new_value=final_value,
                    confidence=confidence,
                    source_extraction_id=extraction_id,
                    update_type=ProfileUpdateType.FACT,
                    resolution_strategy=strategy,
                    reason=reason
                ))
                
                # 应用变更
                if strategy != ConflictResolutionStrategy.REJECT:
                    profile_data["facts"][key] = final_value
                    
                    # 对于稳定事实，使用版本化
                    if is_stable and strategy == ConflictResolutionStrategy.VERSION and conflict.has_conflict:
                        version_manager.archive_current_version(
                            session,
                            target_user_id,
                            current_profile,
                            f"Fact update: {key} changed from '{conflict.existing_value}' to '{final_value}'",
                            extraction_id
                        )
            
            # 4. 保存更新后的档案
            new_version = current_profile["version"] + 1
            
            session.execute(
                text("""
                    INSERT INTO user_profiles (user_id, profile, version, updated_at, created_at)
                    VALUES (:user_id, :profile, :version, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        profile = EXCLUDED.profile,
                        version = EXCLUDED.version,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "user_id": target_user_id,
                    "profile": profile_data,
                    "version": new_version,
                }
            )
            
            session.commit()
            
            # 5. 记录审计日志
            audit_log(
                event="profile.update",
                outcome="success",
                details={
                    "user_id": target_user_id,
                    "extraction_id": extraction_id,
                    "version": new_version,
                    "changes": [
                        {
                            "field_type": c.field_type,
                            "field_key": c.field_key,
                            "old_value": str(c.old_value)[:100] if c.old_value else None,
                            "new_value": str(c.new_value)[:100] if c.new_value else None,
                            "strategy": c.resolution_strategy.value,
                            "reason": c.reason,
                        }
                        for c in changes
                    ],
                }
            )
            
            # 更新任务状态
            if job_id:
                update_consolidation_job_status(job_id, TaskStatus.SUCCEEDED)
            
            _logger.info(f"Profile upsert completed for user_id={target_user_id}, version={new_version}")
            
            return {
                "user_id": target_user_id,
                "extraction_id": extraction_id,
                "version": new_version,
                "status": "succeeded",
                "changes_count": len(changes),
                "changes": [
                    {
                        "field_type": c.field_type,
                        "field_key": c.field_key,
                        "resolution_strategy": c.resolution_strategy.value,
                    }
                    for c in changes
                ],
            }
            
        finally:
            session.close()
            
    except AppError:
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        raise
    except Exception as e:
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        
        _logger.error(f"Profile upsert failed for extraction {extraction_id}: {e}")
        raise AppError(
            code=ErrorCode.PROFILE_UPDATE_FAILED,
            message=f"Profile upsert failed: {str(e)}",
            status_code=500
        ) from e


def enqueue_profile_update(
    extraction_id: str | uuid.UUID,
    user_id: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL
) -> Any:
    """将档案更新任务入队
    
    Args:
        extraction_id: 提取ID
        user_id: 用户ID（可选）
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    extraction_id_str = str(extraction_id) if isinstance(extraction_id, uuid.UUID) else extraction_id
    
    return enqueue_task(
        upsert_profile,
        extraction_id_str,
        user_id=user_id,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=300,
        job_meta={"extraction_id": extraction_id_str, "user_id": user_id} if (extraction_id or user_id) else {}
    )


def get_profile_with_history(
    user_id: str,
    include_history: bool = False,
    history_limit: int = 10
) -> dict[str, Any]:
    """获取用户档案及历史版本
    
    Args:
        user_id: 用户ID
        include_history: 是否包含历史版本
        history_limit: 历史版本数量限制
        
    Returns:
        档案数据
    """
    db = get_database()
    session = db.get_session()
    
    try:
        from sqlalchemy import text
        
        # 获取当前档案
        result = session.execute(
            text("""
                SELECT user_id, profile, version, updated_at, created_at
                FROM user_profiles
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).first()
        
        if not result:
            return {
                "user_id": user_id,
                "profile": {"facts": {}, "preferences": {}, "constraints": {}},
                "version": 0,
                "exists": False,
            }
        
        profile = {
            "user_id": result[0],
            "profile": result[1],
            "version": result[2],
            "updated_at": result[3].isoformat() if result[3] else None,
            "created_at": result[4].isoformat() if result[4] else None,
            "exists": True,
        }
        
        # 获取历史版本
        if include_history:
            version_manager = ProfileVersionManager()
            profile["history"] = version_manager.get_profile_history(
                session, user_id, history_limit
            )
        
        return profile
        
    finally:
        session.close()
