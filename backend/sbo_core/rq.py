"""
Redis Queue (RQ) 集成模块

提供与 tasks_framework 的向后兼容接口
"""

from __future__ import annotations

# 从任务框架重新导出
from sbo_core.tasks_framework import (
    get_redis_connection as get_redis,
    get_queue,
    get_queue_by_priority,
    get_all_queues,
    enqueue_task,
    TaskPriority,
    TaskStatus,
    QUEUE_DEFAULT,
    QUEUE_HIGH,
    QUEUE_LOW,
    QUEUE_ARCHIVE,
    QUEUE_LIFECYCLE,
    QUEUE_RERANK,
)

__all__ = [
    "get_redis",
    "get_queue",
    "get_queue_by_priority",
    "get_all_queues",
    "enqueue_task",
    "TaskPriority",
    "TaskStatus",
    "QUEUE_DEFAULT",
    "QUEUE_HIGH",
    "QUEUE_LOW",
    "QUEUE_ARCHIVE",
    "QUEUE_LIFECYCLE",
    "QUEUE_RERANK",
]
