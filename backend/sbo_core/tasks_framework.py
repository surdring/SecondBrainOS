"""
Redis Queue (RQ) 任务框架 - 4.1 Redis Queue 工作框架实现

该模块提供：
1. RQ Worker 配置和队列管理
2. 任务失败重试机制
3. 任务监控和日志
4. 异步任务基类和装饰器
"""

from __future__ import annotations

import functools
import logging
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, TypeVar

from redis import Redis
from rq import Queue, Retry
from rq.job import Job
from rq.worker import Worker

from sbo_core.config import load_settings
from sbo_core.database import get_database, ConsolidationJob
from sbo_core.audit import audit_log

_logger = logging.getLogger("sbo_core.tasks")

F = TypeVar("F", bound=Callable[..., Any])


class TaskStatus(str, Enum):
    """任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class TaskPriority(str, Enum):
    """任务优先级"""
    HIGH = "high"      # Cross-Encoder 重排、对话归档
    NORMAL = "normal"  # 一般巩固任务
    LOW = "low"        # 生命周期更新


# 队列名称常量
QUEUE_DEFAULT = "sbo_default"
QUEUE_HIGH = "sbo_high"
QUEUE_LOW = "sbo_low"
QUEUE_ARCHIVE = "sbo_archive"  # 对话归档专用队列
QUEUE_LIFECYCLE = "sbo_lifecycle"  # 生命周期任务队列
QUEUE_RERANK = "sbo_rerank"  # 重排任务队列


def get_redis_connection() -> Redis:
    """获取 Redis 连接"""
    settings = load_settings()
    return Redis.from_url(settings.redis_url, decode_responses=False)


def get_queue(name: str | None = None) -> Queue:
    """
    获取 RQ 队列
    
    Args:
        name: 队列名称，默认为 sbo_default
        
    Returns:
        RQ Queue 实例
    """
    settings = load_settings()
    queue_name = name or settings.rq_queue_name
    return Queue(queue_name, connection=get_redis_connection())


def get_queue_by_priority(priority: TaskPriority) -> Queue:
    """根据优先级获取队列"""
    mapping = {
        TaskPriority.HIGH: QUEUE_HIGH,
        TaskPriority.NORMAL: QUEUE_DEFAULT,
        TaskPriority.LOW: QUEUE_LOW,
    }
    return get_queue(mapping.get(priority, QUEUE_DEFAULT))


def get_all_queues() -> list[Queue]:
    """获取所有队列实例"""
    return [
        get_queue(QUEUE_HIGH),
        get_queue(QUEUE_DEFAULT),
        get_queue(QUEUE_LOW),
        get_queue(QUEUE_ARCHIVE),
        get_queue(QUEUE_LIFECYCLE),
        get_queue(QUEUE_RERANK),
    ]


def get_retry_strategy(max_retries: int = 3, intervals: list[int] | None = None) -> Retry:
    """
    获取重试策略
    
    Args:
        max_retries: 最大重试次数
        intervals: 重试间隔（秒），默认 [30, 60, 120]
        
    Returns:
        RQ Retry 配置
    """
    if intervals is None:
        intervals = [30, 60, 120]  # 30秒、1分钟、2分钟
    
    return Retry(max=max_retries, interval=intervals)


def enqueue_task(
    func: Callable[..., Any],
    *args: Any,
    queue_name: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    job_id: str | None = None,
    timeout: int = 600,  # 默认 10 分钟
    result_ttl: int = 86400,  # 结果保留 24 小时
    failure_ttl: int = 604800,  # 失败任务保留 7 天
    max_retries: int = 3,
    retry_intervals: list[int] | None = None,
    job_meta: dict[str, Any] | None = None,
    **kwargs: Any
) -> Job:
    """
    将任务入队
    
    Args:
        func: 任务函数
        args: 位置参数
        queue_name: 队列名称（可选）
        priority: 任务优先级
        job_id: 自定义 job ID
        timeout: 任务超时（秒）
        result_ttl: 结果保留时间（秒）
        failure_ttl: 失败任务保留时间（秒）
        max_retries: 最大重试次数
        retry_intervals: 重试间隔列表
        job_meta: 任务元数据
        kwargs: 关键字参数
        
    Returns:
        RQ Job 实例
    """
    queue = get_queue(queue_name) if queue_name else get_queue_by_priority(priority)
    
    retry = get_retry_strategy(max_retries, retry_intervals)
    
    meta = job_meta or {}
    meta.update({
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "priority": priority.value,
    })
    
    job = queue.enqueue(
        func,
        *args,
        job_id=job_id,
        timeout=timeout,
        result_ttl=result_ttl,
        failure_ttl=failure_ttl,
        retry=retry,
        meta=meta,
        **kwargs
    )
    
    _logger.info(
        f"Task enqueued: {func.__name__} (job_id={job.id}, queue={queue.name})"
    )
    
    audit_log(
        event="task.enqueue",
        outcome="success",
        details={
            "job_id": job.id,
            "function": func.__name__,
            "queue": queue.name,
            "priority": priority.value,
            "timeout": timeout,
        }
    )
    
    return job


def task_wrapper(
    func: F | None = None,
    *,
    max_retries: int = 3,
    retry_intervals: list[int] | None = None,
    timeout: int = 600,
    persist_result: bool = True,
) -> F | Callable[[F], F]:
    """
    任务包装器 - 提供统一的错误处理、重试和监控
    
    可作为装饰器使用：
        @task_wrapper(max_retries=3)
        def my_task():
            pass
    
    Args:
        func: 原始任务函数（可选，用于装饰器模式）
        max_retries: 最大重试次数
        retry_intervals: 重试间隔
        timeout: 任务超时
        persist_result: 是否持久化结果
        
    Returns:
        包装后的任务函数或装饰器
    """
    def decorator(f: F) -> F:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            job = None
            try:
                # 尝试从当前执行环境获取 job 信息
                from rq import get_current_job
                job = get_current_job()
            except Exception:
                pass
            
            job_id = job.id if job else "unknown"
            start_time = datetime.now(timezone.utc)
            
            _logger.info(f"Task started: {f.__name__} (job_id={job_id})")
            
            try:
                # 执行实际任务
                result = f(*args, **kwargs)
                
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                
                _logger.info(
                    f"Task completed: {f.__name__} (job_id={job_id}, duration={duration_ms}ms)"
                )
                
                audit_log(
                    event="task.complete",
                    outcome="success",
                    details={
                        "job_id": job_id,
                        "function": f.__name__,
                        "duration_ms": duration_ms,
                    }
                )
                
                return result
                
            except Exception as e:
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                error_msg = str(e)
                tb = traceback.format_exc()
                
                _logger.error(
                    f"Task failed: {f.__name__} (job_id={job_id}, duration={duration_ms}ms, error={error_msg})"
                )
                
                audit_log(
                    event="task.fail",
                    outcome="fail",
                    details={
                        "job_id": job_id,
                        "function": f.__name__,
                        "duration_ms": duration_ms,
                        "error": error_msg,
                        "traceback": tb,
                        "retry_count": getattr(job, "retry_count", 0) if job else 0,
                    }
                )
                
                # 重新抛出异常以触发 RQ 重试机制
                raise
        
        # 添加元数据
        wrapper._task_config = {
            "max_retries": max_retries,
            "retry_intervals": retry_intervals,
            "timeout": timeout,
            "persist_result": persist_result,
        }
        
        return wrapper  # type: ignore[return-value]
    
    if func is not None:
        return decorator(func)
    return decorator


def update_consolidation_job_status(
    job_id: str,
    status: TaskStatus,
    error_message: str | None = None,
) -> None:
    """
    更新巩固任务状态
    
    Args:
        job_id: 任务 ID
        status: 新状态
        error_message: 错误信息（可选）
    """
    try:
        db = get_database()
        session = db.get_session()
        
        try:
            job = session.query(ConsolidationJob).filter(
                ConsolidationJob.id == job_id
            ).first()
            
            if job:
                job.status = status.value
                
                if status == TaskStatus.RUNNING and not job.started_at:
                    job.started_at = datetime.now(timezone.utc)
                
                if status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                    job.completed_at = datetime.now(timezone.utc)
                
                if error_message:
                    job.error_message = error_message
                
                if status == TaskStatus.RETRYING:
                    job.attempts = (job.attempts or 0) + 1
                
                session.commit()
        finally:
            session.close()
    except Exception as e:
        _logger.error(f"Failed to update job status: {e}")


class TaskMonitor:
    """任务监控器"""
    
    @staticmethod
    def get_queue_stats() -> dict[str, Any]:
        """获取队列统计信息"""
        queues = get_all_queues()
        stats = {}
        
        for queue in queues:
            stats[queue.name] = {
                "queued": queue.count,
                "scheduled": queue.scheduled_job_registry.count,
                "started": queue.started_job_registry.count,
                "finished": queue.finished_job_registry.count,
                "failed": queue.failed_job_registry.count,
                "deferred": queue.deferred_job_registry.count,
            }
        
        return stats
    
    @staticmethod
    def get_failed_jobs(queue_name: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """获取失败的任务列表"""
        queue = get_queue(queue_name) if queue_name else get_queue()
        
        failed_jobs = []
        for job_id in queue.failed_job_registry.get_job_ids()[:limit]:
            try:
                job = Job.fetch(job_id, connection=queue.connection)
                failed_jobs.append({
                    "job_id": job_id,
                    "function": job.func_name if job else None,
                    "created_at": job.created_at.isoformat() if job and job.created_at else None,
                    "exc_info": job.exc_info if job else None,
                })
            except Exception:
                failed_jobs.append({"job_id": job_id, "error": "Failed to fetch job"})
        
        return failed_jobs
    
    @staticmethod
    def requeue_failed_jobs(queue_name: str | None = None, limit: int = 100) -> int:
        """重新入队失败的任务"""
        queue = get_queue(queue_name) if queue_name else get_queue()
        
        count = 0
        for job_id in queue.failed_job_registry.get_job_ids()[:limit]:
            try:
                queue.failed_job_registry.requeue(job_id)
                count += 1
                
                audit_log(
                    event="task.requeue",
                    outcome="success",
                    details={"job_id": job_id, "queue": queue.name}
                )
            except Exception as e:
                _logger.error(f"Failed to requeue job {job_id}: {e}")
        
        return count


def run_worker(
    queues: list[str] | None = None,
    with_scheduler: bool = True,
    burst: bool = False,
    name: str | None = None,
) -> None:
    """
    运行 RQ Worker
    
    Args:
        queues: 要监听的队列列表，默认监听所有队列
        with_scheduler: 是否启用调度器
        burst: 是否 burst 模式（处理完当前任务后退出）
        name: Worker 名称
    """
    if queues is None:
        queues = [QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW, QUEUE_ARCHIVE, QUEUE_LIFECYCLE, QUEUE_RERANK]
    
    redis_conn = get_redis_connection()
    
    with Worker([get_queue(q) for q in queues], connection=redis_conn, name=name) as worker:
        _logger.info(f"Worker started: {worker.name}, listening on queues: {queues}")
        worker.work(with_scheduler=with_scheduler, burst=burst)


if __name__ == "__main__":
    # 直接运行 worker 用于本地开发
    run_worker()
