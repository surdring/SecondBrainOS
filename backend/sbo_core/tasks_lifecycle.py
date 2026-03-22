"""
生命周期/衰减任务实现 - 4.1.3

功能：
1. time-decay re-ranking（阶段 1：简单、可解释）
2. 访问计数/最后访问时间的异步更新（避免热路径延迟）
3. 确保生命周期字段不破坏 raw_events 可回放原则
4. 为阶段 2（access_count/last_accessed_at 强化衰减）预留接口
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sbo_core.tasks_framework import task_wrapper, enqueue_task, QUEUE_LIFECYCLE, TaskPriority
from sbo_core.audit import audit_log
from sbo_core.database import get_database, EvidenceAccessStats, RawEvent
from sbo_core.config import load_settings

_logger = logging.getLogger("sbo_core.lifecycle_tasks")


@dataclass
class TimeDecayConfig:
    """时间衰减配置"""
    decay_rate: float = 0.1  # 每天衰减率
    semantic_weight: float = 0.8  # 语义分数权重
    time_weight: float = 0.2  # 时间分数权重
    max_days: int = 365  # 最大考虑天数


@dataclass
class LifecycleScore:
    """生命周期评分结果"""
    evidence_id: str
    original_score: float
    time_weight: float
    final_score: float
    days_ago: int
    access_count: int | None  # 阶段 2 使用
    last_accessed_at: datetime | None  # 阶段 2 使用


class LifecycleService:
    """生命周期服务"""
    
    def __init__(self):
        self._config = TimeDecayConfig()
    
    def calculate_time_decay_score(
        self,
        occurred_at: datetime,
        reference_time: datetime | None = None,
    ) -> float:
        """
        计算时间衰减分数
        
        阶段 1 实现：简单指数衰减
        score = exp(-decay_rate * days_ago)
        
        Args:
            occurred_at: 发生时间
            reference_time: 参考时间（默认当前时间）
            
        Returns:
            时间衰减分数 (0-1)
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        # 确保都有时区信息
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        
        days_ago = (reference_time - occurred_at).days
        days_ago = min(days_ago, self._config.max_days)
        days_ago = max(days_ago, 0)
        
        # 指数衰减公式
        time_score = math.exp(-self._config.decay_rate * days_ago)
        
        return time_score
    
    def apply_time_decay_reranking(
        self,
        candidates: list[dict[str, Any]],
        reference_time: datetime | None = None,
    ) -> list[LifecycleScore]:
        """
        应用时间衰减重排
        
        final_score = semantic_score * semantic_weight + time_score * time_weight
        
        Args:
            candidates: 候选列表（已融合或重排后的结果）
            reference_time: 参考时间
            
        Returns:
            带有生命周期评分的候选列表
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        results: list[LifecycleScore] = []
        
        for candidate in candidates:
            evidence_id = candidate.get("evidence_id", "")
            scores = candidate.get("scores", {})
            
            # 获取原始分数（semantic/fusion/hybrid）
            original_score = scores.get("hybrid_score") or scores.get("fusion_score") or scores.get("semantic_score", 0.0)
            
            # 解析发生时间
            occurred_at_str = candidate.get("occurred_at")
            if occurred_at_str:
                if isinstance(occurred_at_str, str):
                    try:
                        occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                    except Exception:
                        occurred_at = reference_time
                elif isinstance(occurred_at_str, datetime):
                    occurred_at = occurred_at_str
                else:
                    occurred_at = reference_time
            else:
                occurred_at = reference_time
            
            # 计算时间衰减分数
            time_score = self.calculate_time_decay_score(occurred_at, reference_time)
            
            # 混合评分
            final_score = (
                original_score * self._config.semantic_weight +
                time_score * self._config.time_weight
            )
            
            days_ago = (reference_time - occurred_at).days if occurred_at <= reference_time else 0
            
            lifecycle_score = LifecycleScore(
                evidence_id=evidence_id,
                original_score=original_score,
                time_weight=time_score,
                final_score=final_score,
                days_ago=max(days_ago, 0),
                access_count=None,  # 阶段 2 填充
                last_accessed_at=None,  # 阶段 2 填充
            )
            
            results.append(lifecycle_score)
        
        # 按最终分数排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        return results
    
    # ==================== 阶段 2 预留接口 ====================
    
    def calculate_reinforcement_score(
        self,
        access_count: int,
        last_accessed_at: datetime,
        occurred_at: datetime,
        reference_time: datetime | None = None,
    ) -> float:
        """
        计算强化衰减分数（阶段 2）
        
        结合访问频率和最后访问时间的综合评分
        
        Args:
            access_count: 访问次数
            last_accessed_at: 最后访问时间
            occurred_at: 原始发生时间
            reference_time: 参考时间
            
        Returns:
            强化衰减分数
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        # 基础时间衰减
        base_decay = self.calculate_time_decay_score(occurred_at, reference_time)
        
        # 访问频率提升
        # 访问次数越多，衰减越慢（记忆更持久）
        access_boost = min(math.log1p(access_count) / 5.0, 0.3)  # 最大 0.3 的提升
        
        # 近期访问提升
        days_since_last_access = (reference_time - last_accessed_at).days
        recency_boost = math.exp(-0.05 * days_since_last_access) * 0.2  # 近期访问额外 0.2
        
        # 综合分数
        reinforced_score = base_decay * (1 + access_boost) + recency_boost
        
        return min(reinforced_score, 1.0)
    
    async def get_access_stats(
        self,
        user_id: str,
        evidence_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """
        获取访问统计（阶段 2）
        
        Args:
            user_id: 用户 ID
            evidence_ids: 证据 ID 列表
            
        Returns:
            访问统计字典 {evidence_id: {access_count, last_accessed_at}}
        """
        try:
            db = get_database()
            session = db.get_session()
            
            try:
                stats: dict[str, dict[str, Any]] = {}
                
                for evidence_id in evidence_ids:
                    row = (
                        session.query(EvidenceAccessStats)
                        .filter(
                            EvidenceAccessStats.user_id == user_id,
                            EvidenceAccessStats.evidence_id == evidence_id,
                        )
                        .first()
                    )
                    
                    if row:
                        stats[evidence_id] = {
                            "access_count": row.access_count or 0,
                            "last_accessed_at": row.last_accessed_at.isoformat() if row.last_accessed_at else None,
                        }
                    else:
                        stats[evidence_id] = {
                            "access_count": 0,
                            "last_accessed_at": None,
                        }
                
                return stats
            finally:
                session.close()
        except Exception as e:
            _logger.error(f"Failed to get access stats: {e}")
            return {eid: {"access_count": 0, "last_accessed_at": None} for eid in evidence_ids}


class AccessTrackingService:
    """访问追踪服务 - 异步更新访问统计"""
    
    async def record_access_batch(
        self,
        user_id: str,
        evidence_ids: list[str],
        query_context: dict[str, Any] | None = None,
    ) -> int:
        """
        批量记录访问
        
        Args:
            user_id: 用户 ID
            evidence_ids: 证据 ID 列表
            query_context: 查询上下文（可选）
            
        Returns:
            成功更新的记录数
        """
        if not user_id or not evidence_ids:
            return 0
        
        now = datetime.now(timezone.utc)
        
        try:
            db = get_database()
            session = db.get_session()
            
            updated = 0
            
            try:
                for evidence_id in evidence_ids:
                    row = (
                        session.query(EvidenceAccessStats)
                        .filter(
                            EvidenceAccessStats.user_id == user_id,
                            EvidenceAccessStats.evidence_id == evidence_id,
                        )
                        .first()
                    )
                    
                    if row is None:
                        # 创建新记录
                        row = EvidenceAccessStats(
                            user_id=user_id,
                            evidence_id=evidence_id,
                            access_count=1,
                            last_accessed_at=now,
                        )
                        session.add(row)
                    else:
                        # 更新现有记录
                        row.access_count = (row.access_count or 0) + 1
                        row.last_accessed_at = now
                    
                    updated += 1
                
                session.commit()
                
                audit_log(
                    event="lifecycle.access_record",
                    outcome="success",
                    details={
                        "user_id": user_id,
                        "evidence_count": len(evidence_ids),
                        "query_context": query_context,
                    }
                )
                
                return updated
                
            except Exception as e:
                session.rollback()
                raise
            finally:
                session.close()
                
        except Exception as e:
            _logger.error(f"Failed to record access batch: {e}")
            audit_log(
                event="lifecycle.access_record",
                outcome="fail",
                details={
                    "user_id": user_id,
                    "evidence_count": len(evidence_ids),
                    "error": str(e),
                }
            )
            return 0


# 全局服务实例
lifecycle_service = LifecycleService()
access_tracking_service = AccessTrackingService()


@task_wrapper(max_retries=3, timeout=60)
def record_access_task(
    user_id: str,
    evidence_ids: list[str],
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    异步记录访问统计任务
    
    Args:
        user_id: 用户 ID
        evidence_ids: 证据 ID 列表
        query_context: 查询上下文
        
    Returns:
        更新结果
    """
    import asyncio
    
    updated = asyncio.run(access_tracking_service.record_access_batch(
        user_id, evidence_ids, query_context
    ))
    
    return {
        "user_id": user_id,
        "evidence_ids": evidence_ids,
        "updated_count": updated,
    }


@task_wrapper(max_retries=2, timeout=300)
def lifecycle_decay_recalculation_task(
    user_id: str | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    生命周期衰减重新计算任务（后台优化用）
    
    阶段 2：可以定期批量重新计算所有证据的生命周期分数
    
    Args:
        user_id: 用户 ID（可选，None 表示所有用户）
        evidence_ids: 证据 ID 列表（可选，None 表示所有证据）
        
    Returns:
        计算结果
    """
    # TODO: 阶段 2 实现
    _logger.info(f"Lifecycle decay recalculation triggered for user={user_id}, evidence_count={len(evidence_ids) if evidence_ids else 'all'}")
    
    audit_log(
        event="lifecycle.recalc",
        outcome="success",
        details={
            "user_id": user_id,
            "evidence_count": len(evidence_ids) if evidence_ids else None,
            "note": "Stage 2 placeholder",
        }
    )
    
    return {
        "status": "placeholder",
        "user_id": user_id,
        "evidence_count": len(evidence_ids) if evidence_ids else None,
    }


def enqueue_access_tracking(
    user_id: str,
    evidence_ids: list[str],
    query_context: dict[str, Any] | None = None,
) -> Any:
    """
    将访问追踪任务入队
    
    Args:
        user_id: 用户 ID
        evidence_ids: 证据 ID 列表
        query_context: 查询上下文
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        record_access_task,
        user_id,
        evidence_ids,
        query_context,
        queue_name=QUEUE_LIFECYCLE,
        priority=TaskPriority.LOW,
        timeout=60,  # 1 分钟
        max_retries=3,
        retry_intervals=[5, 15, 30],
    )


def enqueue_lifecycle_recalculation(
    user_id: str | None = None,
    evidence_ids: list[str] | None = None,
) -> Any:
    """
    将生命周期重新计算任务入队
    
    Args:
        user_id: 用户 ID
        evidence_ids: 证据 ID 列表
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        lifecycle_decay_recalculation_task,
        user_id,
        evidence_ids,
        queue_name=QUEUE_LIFECYCLE,
        priority=TaskPriority.LOW,
        timeout=300,  # 5 分钟
        max_retries=2,
    )
