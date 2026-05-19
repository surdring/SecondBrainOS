"""
向量嵌入任务实现 - 4.6

功能：
1. 实现 embed_event(event_id) 任务
2. 集成 SiliconFlow embeddings API（通过 embeddings_client）
3. 实现失败不阻塞策略
4. 支持批量重跑机制
5. 实现 embeddings 回放重建与审计（4.6.1）

依赖需求：3.5, 4.1.2, 3.5.2
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from enum import Enum

from sqlalchemy import text

from sbo_core.tasks_framework import (
    task_wrapper, enqueue_task, QUEUE_DEFAULT, TaskPriority, TaskStatus,
    update_consolidation_job_status
)
from sbo_core.audit import audit_log
from sbo_core.database import get_database, RawEvent, Embedding
from sbo_core.embeddings_client import get_embeddings_client, embed_text, EmbeddingsError
from sbo_core.errors import ErrorCode, AppError

_logger = logging.getLogger("sbo_core.embedding_tasks")


class EmbeddingErrorType(str, Enum):
    """Embedding 错误类型"""
    TIMEOUT = "timeout"              # 超时
    RATE_LIMITED = "rate_limited"    # 限流
    AUTH_FAILED = "auth_failed"      # 认证失败
    INVALID_INPUT = "invalid_input"  # 无效输入
    UNAVAILABLE = "unavailable"      # 服务不可用
    UNKNOWN = "unknown"              # 未知错误


class RetryPriority(str, Enum):
    """重试优先级"""
    HIGH = "high"      # 高优先级（临时性错误）
    MEDIUM = "medium"  # 中优先级
    LOW = "low"        # 低优先级（永久性错误）


class EmbeddingJobResult:
    """Embedding 任务结果"""
    def __init__(
        self,
        event_id: str,
        success: bool,
        embedding_id: str | None = None,
        model_name: str | None = None,
        dimensions: int = 0,
        error_message: str | None = None,
        rerun_count: int = 0,
    ):
        self.event_id = event_id
        self.success = success
        self.embedding_id = embedding_id
        self.model_name = model_name
        self.dimensions = dimensions
        self.error_message = error_message
        self.rerun_count = rerun_count


def _classify_embedding_error(error: Exception) -> tuple[str, str]:
    """
    分类 embedding 错误并确定重试优先级
    
    Args:
        error: 异常对象
        
    Returns:
        (error_type, retry_priority) 元组
    """
    if isinstance(error, EmbeddingsError):
        error_type = error.error_type or EmbeddingErrorType.UNKNOWN
        
        # 根据错误类型确定重试优先级
        high_priority_errors = ["timeout", "rate_limited", "unavailable"]
        low_priority_errors = ["auth_failed", "invalid_input"]
        
        if error_type in high_priority_errors:
            return error_type, RetryPriority.HIGH
        elif error_type in low_priority_errors:
            return error_type, RetryPriority.LOW
        else:
            return error_type, RetryPriority.MEDIUM
    
    error_msg = str(error).lower()
    
    # 根据错误消息分类
    if "timeout" in error_msg or "timed out" in error_msg:
        return EmbeddingErrorType.TIMEOUT, RetryPriority.HIGH
    elif "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
        return EmbeddingErrorType.RATE_LIMITED, RetryPriority.HIGH
    elif "auth" in error_msg or "401" in error_msg or "unauthorized" in error_msg:
        return EmbeddingErrorType.AUTH_FAILED, RetryPriority.LOW
    elif "invalid" in error_msg or "bad request" in error_msg or "400" in error_msg:
        return EmbeddingErrorType.INVALID_INPUT, RetryPriority.LOW
    elif "unavailable" in error_msg or "5" in error_msg or "service" in error_msg:
        return EmbeddingErrorType.UNAVAILABLE, RetryPriority.HIGH
    else:
        return EmbeddingErrorType.UNKNOWN, RetryPriority.MEDIUM


@task_wrapper(max_retries=3, timeout=30)  # 30s timeout per spec
def embed_event(event_id: str, job_id: str | None = None, is_rerun: bool = False) -> dict[str, Any]:
    """
    向量嵌入任务 - 为指定事件生成向量嵌入
    
    失败不阻塞策略：
    - embedding 失败不影响 raw_events 落库与其它抽取步骤的执行
    - 失败时记录错误信息，允许后续批量重跑
    
    Args:
        event_id: 事件ID（字符串格式UUID）
        job_id: 嵌入任务ID（可选）
        is_rerun: 是否为重跑（用于审计）
        
    Returns:
        任务执行结果
    """
    _logger.info(f"Starting embed_event for event_id={event_id}, is_rerun={is_rerun}")
    
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError as e:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid event_id format: {event_id}",
            status_code=400
        ) from e
    
    # 更新任务状态
    if job_id:
        update_consolidation_job_status(job_id, TaskStatus.RUNNING)
    
    db = get_database()
    session = db.get_session()
    
    error_type: str | None = None
    retry_priority: str | None = None
    
    try:
        # 1. 获取原始事件
        event = session.query(RawEvent).filter(RawEvent.id == event_uuid).first()
        
        if not event:
            raise AppError(
                code=ErrorCode.EVENT_NOT_FOUND,
                message=f"Event not found: {event_id}",
                status_code=404
            )
        
        if event.deleted_at:
            _logger.warning(f"Event {event_id} is soft-deleted, skipping embedding")
            return {
                "event_id": event_id,
                "status": "skipped",
                "reason": "event_soft_deleted"
            }
        
        if not event.content or not event.content.strip():
            _logger.warning(f"Event {event_id} has empty content, skipping embedding")
            return {
                "event_id": event_id,
                "status": "skipped",
                "reason": "empty_content"
            }
        
        # 2. 检查是否已有 embedding（非重跑情况下）
        if not is_rerun:
            existing = session.query(Embedding).filter(Embedding.event_id == event_uuid).first()
            if existing:
                _logger.info(f"Embedding already exists for event {event_id}, skipping")
                return {
                    "event_id": event_id,
                    "status": "skipped",
                    "reason": "embedding_exists",
                    "embedding_id": str(existing.id)
                }
        
        # 3. 生成向量嵌入（失败不阻塞）
        embedding_vector = None
        client = None
        error_msg = None
        error_type = None
        retry_priority = None
        
        try:
            client = get_embeddings_client()
            embedding_vector = client.embed_single(event.content)
            
            if embedding_vector is None:
                error_msg = "Embedding generation returned None"
                error_type = EmbeddingErrorType.INVALID_INPUT
                retry_priority = RetryPriority.LOW
                _logger.warning(f"{error_msg} for event {event_id}")
                
        except AppError as e:
            # 配置错误等，记录但不阻塞
            error_msg = f"Embedding configuration error: {e.message}"
            error_type, retry_priority = EmbeddingErrorType.UNAVAILABLE, RetryPriority.HIGH
            _logger.error(error_msg)
            
        except EmbeddingsError as e:
            # API 调用错误，记录但不阻塞
            error_msg = f"Embeddings API error: {e.message}"
            error_type, retry_priority = _classify_embedding_error(e)
            _logger.error(error_msg)
            
        except Exception as e:
            # 其他错误，记录但不阻塞
            error_msg = f"Unexpected embedding error: {str(e)}"
            error_type, retry_priority = _classify_embedding_error(e)
            _logger.error(error_msg)
        
        # 4. 保存 embedding 到数据库
        if embedding_vector:
            # 获取或创建 embedding 记录
            embedding_record = session.query(Embedding).filter(
                Embedding.event_id == event_uuid
            ).first()
            
            now = datetime.now(timezone.utc)
            
            if embedding_record:
                # 更新现有记录（重跑场景）
                embedding_record.embedding = embedding_vector
                embedding_record.model_name = client.model if client else "unknown"
                embedding_record.dimensions = len(embedding_vector)
                embedding_record.updated_at = now
                embedding_record.rerun_count = (embedding_record.rerun_count or 0) + (1 if is_rerun else 0)
                embedding_record.last_rerun_at = now if is_rerun else embedding_record.last_rerun_at
                embedding_record.error_message = None  # 清除错误信息
            else:
                # 创建新记录
                embedding_record = Embedding(
                    event_id=event_uuid,
                    embedding=embedding_vector,
                    model_name=client.model if client else "unknown",
                    dimensions=len(embedding_vector),
                    rerun_count=0,
                    last_rerun_at=None,
                    error_message=None,
                )
                session.add(embedding_record)
            
            session.commit()
            
            # 刷新以获取 ID
            session.refresh(embedding_record)
            
            # 5. 记录审计日志
            audit_log(
                event="embedding.complete",
                outcome="success",
                details={
                    "event_id": event_id,
                    "embedding_id": str(embedding_record.id),
                    "model": embedding_record.model_name,
                    "dimensions": embedding_record.dimensions,
                    "is_rerun": is_rerun,
                    "rerun_count": embedding_record.rerun_count,
                }
            )
            
            # 更新任务状态
            if job_id:
                update_consolidation_job_status(job_id, TaskStatus.SUCCEEDED)
            
            _logger.info(f"Embedding completed for event_id={event_id}")
            
            return {
                "event_id": event_id,
                "status": "succeeded",
                "embedding_id": str(embedding_record.id),
                "model": embedding_record.model_name,
                "dimensions": embedding_record.dimensions,
                "is_rerun": is_rerun,
            }
        else:
            # 生成失败，记录错误但不阻塞
            _logger.warning(f"Embedding failed for event {event_id}, recording error for retry")
            
            # 保存失败记录（用于后续批量重跑）
            embedding_record = session.query(Embedding).filter(
                Embedding.event_id == event_uuid
            ).first()
            
            if embedding_record:
                embedding_record.error_message = error_msg
                embedding_record.error_type = error_type
                embedding_record.retry_priority = retry_priority
                embedding_record.updated_at = datetime.now(timezone.utc)
            else:
                # 创建带有错误信息的占位记录
                embedding_record = Embedding(
                    event_id=event_uuid,
                    embedding=None,
                    model_name="unknown",
                    dimensions=0,
                    error_message=error_msg,
                    error_type=error_type,
                    retry_priority=retry_priority,
                )
                session.add(embedding_record)
            
            session.commit()
            
            # 记录审计日志（失败）
            audit_log(
                event="embedding.failed",
                outcome="fail",
                details={
                    "event_id": event_id,
                    "error": error_msg,
                    "is_rerun": is_rerun,
                }
            )
            
            # 更新任务状态为失败（但不抛出异常，不阻塞）
            if job_id:
                update_consolidation_job_status(job_id, TaskStatus.FAILED, error_msg)
            
            # 返回失败状态但不抛出异常（失败不阻塞策略）
            return {
                "event_id": event_id,
                "status": "failed",
                "error": error_msg,
                "retryable": True,
                "is_rerun": is_rerun,
            }
        
    except AppError:
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED)
        raise
    except Exception as e:
        error_msg = f"Embedding task error: {str(e)}"
        _logger.error(f"{error_msg} for event {event_id}")
        
        if job_id:
            update_consolidation_job_status(job_id, TaskStatus.FAILED, error_msg)
        
        # 记录审计日志
        audit_log(
            event="embedding.error",
            outcome="fail",
            details={
                "event_id": event_id,
                "error": error_msg,
            }
        )
        
        # 返回失败状态但不抛出异常（失败不阻塞策略）
        return {
            "event_id": event_id,
            "status": "failed",
            "error": error_msg,
            "retryable": True,
            "is_rerun": is_rerun,
        }
    finally:
        session.close()


def enqueue_embed_event(
    event_id: str | uuid.UUID,
    user_id: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL
) -> Any:
    """
    将向量嵌入任务入队
    
    Args:
        event_id: 事件ID
        user_id: 用户ID（可选）
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    event_id_str = str(event_id) if isinstance(event_id, uuid.UUID) else event_id
    
    return enqueue_task(
        embed_event,
        event_id_str,
        is_rerun=False,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=60,
        job_meta={"user_id": user_id, "event_id": event_id_str}
    )


class EmbeddingReplayJob:
    """Embedding 回放重跑作业"""
    
    def __init__(
        self,
        job_id: str,
        time_range_start: datetime | None = None,
        time_range_end: datetime | None = None,
        event_ids: list[str] | None = None,
        only_failed: bool = False,
    ):
        self.job_id = job_id
        self.time_range_start = time_range_start
        self.time_range_end = time_range_end
        self.event_ids = event_ids or []
        self.only_failed = only_failed
        self.total_events = 0
        self.processed_events = 0
        self.succeeded_events = 0
        self.failed_events = 0
        self.errors: list[dict[str, Any]] = []


def persist_batch_progress(
    session: Any,
    job_id: str,
    total_events: int,
    processed_events: int,
    succeeded_events: int,
    failed_events: int,
    last_processed_event_id: str | None = None,
    status: str = "running",
    errors: list[dict] | None = None,
) -> None:
    """持久化批量作业进度到数据库
    
    使用 embeddings 表中的 special 记录存储批量作业进度，
    通过 event_id = NULL 且 model_name = 'batch_job:{job_id}' 标识
    
    Args:
        session: 数据库会话
        job_id: 作业ID
        total_events: 总事件数
        processed_events: 已处理事件数
        succeeded_events: 成功数
        failed_events: 失败数
        last_processed_event_id: 最后处理的事件ID
        status: 作业状态
        errors: 错误列表（只保存最近的几个）
    """
    try:
        # 将进度信息存储在 embedding 记录的 metadata 中
        progress_data = {
            "job_id": job_id,
            "total_events": total_events,
            "processed_events": processed_events,
            "succeeded_events": succeeded_events,
            "failed_events": failed_events,
            "last_processed_event_id": last_processed_event_id,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "progress_percent": round((processed_events / total_events * 100), 2) if total_events > 0 else 0,
            "recent_errors": (errors or [])[:5],  # 只保存最近5个错误
        }
        
        # 使用特殊的 model_name 标记来存储进度
        progress_model_name = f"batch_job:{job_id}"
        
        # 查询现有进度记录
        existing = session.query(Embedding).filter(
            Embedding.model_name == progress_model_name,
            Embedding.event_id.is_(None)  # 进度记录没有关联的 event
        ).first()
        
        if existing:
            # 更新现有记录
            existing.error_message = str(progress_data)  # 借用 error_message 字段存储 JSON
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # 创建新进度记录
            progress_record = Embedding(
                event_id=None,  # 进度记录没有关联事件
                embedding=None,
                model_name=progress_model_name,
                dimensions=0,
                error_message=str(progress_data),
            )
            session.add(progress_record)
        
        session.commit()
        
    except Exception as e:
        _logger.warning(f"Failed to persist batch progress: {e}")
        # 进度保存失败不应中断主流程


def load_batch_checkpoint(
    session: Any,
    job_id: str,
) -> dict[str, Any] | None:
    """加载批量作业检查点
    
    Args:
        session: 数据库会话
        job_id: 作业ID
        
    Returns:
        检查点数据或 None
    """
    try:
        progress_model_name = f"batch_job:{job_id}"
        
        record = session.query(Embedding).filter(
            Embedding.model_name == progress_model_name,
            Embedding.event_id.is_(None)
        ).first()
        
        if record and record.error_message:
            # 解析存储的进度数据
            import ast
            try:
                return ast.literal_eval(record.error_message)
            except Exception:
                return None
        
        return None
        
    except Exception as e:
        _logger.warning(f"Failed to load batch checkpoint: {e}")
        return None


def cleanup_batch_checkpoint(
    session: Any,
    job_id: str,
) -> None:
    """清理已完成的批量作业检查点"""
    try:
        progress_model_name = f"batch_job:{job_id}"
        
        session.query(Embedding).filter(
            Embedding.model_name == progress_model_name,
            Embedding.event_id.is_(None)
        ).delete()
        
        session.commit()
        
    except Exception as e:
        _logger.warning(f"Failed to cleanup batch checkpoint: {e}")


@task_wrapper(max_retries=1, timeout=3600)  # 批量作业允许更长超时
def replay_embeddings_batch(
    time_range_start: str | None = None,
    time_range_end: str | None = None,
    event_ids: list[str] | None = None,
    only_failed: bool = True,
    batch_size: int = 100,
    job_id: str | None = None,
    resume_from_checkpoint: bool = True,  # 新增：是否从检查点恢复
) -> dict[str, Any]:
    """
    Embedding 批量重跑作业 - 4.6.1
    
    从 raw_events 批量回放重跑 embeddings，记录每次回放的范围、结果与失败原因，确保可审计。
    支持断点续传：通过 persist_batch_progress 将进度写入数据库，中断后可从上次位置恢复。
    
    Args:
        time_range_start: 时间范围开始（ISO 格式字符串，可选）
        time_range_end: 时间范围结束（ISO 格式字符串，可选）
        event_ids: 指定的事件ID列表（可选，优先级高于时间范围）
        only_failed: 是否只重跑失败的 embedding（默认 True）
        batch_size: 批处理大小（默认 100）
        job_id: 作业ID（可选）
        resume_from_checkpoint: 是否从上次检查点恢复（默认 True）
        
    Returns:
        批量重跑结果统计
    """
    _logger.info(
        f"Starting replay_embeddings_batch: only_failed={only_failed}, "
        f"batch_size={batch_size}"
    )
    
    # 解析时间范围
    start_dt = None
    end_dt = None
    if time_range_start:
        start_dt = datetime.fromisoformat(time_range_start.replace("Z", "+00:00"))
    if time_range_end:
        end_dt = datetime.fromisoformat(time_range_end.replace("Z", "+00:00"))
    
    # 创建作业记录
    replay_job = EmbeddingReplayJob(
        job_id=job_id or str(uuid.uuid4()),
        time_range_start=start_dt,
        time_range_end=end_dt,
        event_ids=event_ids,
        only_failed=only_failed,
    )
    
    db = get_database()
    session = db.get_session()
    
    try:
        # 0. 尝试加载检查点（断点续传）
        checkpoint = None
        processed_event_ids = set()
        
        if resume_from_checkpoint:
            checkpoint = load_batch_checkpoint(session, replay_job.job_id)
            if checkpoint:
                _logger.info(f"Resuming from checkpoint: job_id={replay_job.job_id}")
                # 恢复之前的进度
                replay_job.processed_events = checkpoint.get("processed_events", 0)
                replay_job.succeeded_events = checkpoint.get("succeeded_events", 0)
                replay_job.failed_events = checkpoint.get("failed_events", 0)
                # 记录已处理的事件ID，避免重复处理
                last_event_id = checkpoint.get("last_processed_event_id")
                if last_event_id:
                    processed_event_ids.add(last_event_id)
                _logger.info(
                    f"Restored progress: processed={replay_job.processed_events}, "
                    f"succeeded={replay_job.succeeded_events}, failed={replay_job.failed_events}"
                )
        
        # 1. 查询需要重跑的事件
        query = session.query(RawEvent).filter(RawEvent.deleted_at.is_(None))
        
        if event_ids:
            # 按指定事件ID过滤
            event_uuids = [uuid.UUID(eid) for eid in event_ids]
            query = query.filter(RawEvent.id.in_(event_uuids))
        else:
            # 按时间范围过滤
            if start_dt:
                query = query.filter(RawEvent.occurred_at >= start_dt)
            if end_dt:
                query = query.filter(RawEvent.occurred_at <= end_dt)
        
        # 如果只重跑失败的，需要关联 embedding 表
        if only_failed:
            query = query.outerjoin(
                Embedding, RawEvent.id == Embedding.event_id
            ).filter(
                (Embedding.id.is_(None)) |  # 没有 embedding 记录
                (Embedding.error_message.isnot(None)) |  # 有错误信息
                (Embedding.embedding.is_(None))  # embedding 为 null
            )
        
        # 获取总数量
        replay_job.total_events = query.count()
        
        if replay_job.total_events == 0:
            _logger.info("No events found for replay")
            return {
                "job_id": replay_job.job_id,
                "status": "succeeded",
                "total_events": 0,
                "processed_events": 0,
                "succeeded_events": 0,
                "failed_events": 0,
                "message": "No events found matching criteria",
            }
        
        _logger.info(f"Found {replay_job.total_events} events to process")
        
        # 2. 分批处理
        offset = 0
        last_event_id: str | None = None
        
        while offset < replay_job.total_events:
            batch = query.offset(offset).limit(batch_size).all()
            
            if not batch:
                break
            
            for event in batch:
                event_id_str = str(event.id)
                last_event_id = event_id_str
                
                # 断点续传：跳过已处理的事件
                if event_id_str in processed_event_ids:
                    continue
                
                replay_job.processed_events += 1
                
                try:
                    # 调用 embed_event 进行重跑
                    result = embed_event(
                        event_id=event_id_str,
                        is_rerun=True,
                    )
                    
                    if result.get("status") == "succeeded":
                        replay_job.succeeded_events += 1
                    else:
                        replay_job.failed_events += 1
                        replay_job.errors.append({
                            "event_id": event_id_str,
                            "error": result.get("error", "Unknown error"),
                        })
                    
                    # 每 10 个事件记录一次进度日志
                    if replay_job.processed_events % 10 == 0:
                        _logger.info(
                            f"Replay progress: {replay_job.processed_events}/{replay_job.total_events} "
                            f"({(replay_job.processed_events / replay_job.total_events * 100):.1f}%) "
                            f"(succeeded: {replay_job.succeeded_events}, failed: {replay_job.failed_events})"
                        )
                    
                    # 每 50 个事件持久化一次进度（断点续传支持）
                    if replay_job.processed_events % 50 == 0:
                        persist_batch_progress(
                            session=session,
                            job_id=replay_job.job_id,
                            total_events=replay_job.total_events,
                            processed_events=replay_job.processed_events,
                            succeeded_events=replay_job.succeeded_events,
                            failed_events=replay_job.failed_events,
                            last_processed_event_id=last_event_id,
                            status="running",
                            errors=replay_job.errors,
                        )
                    
                except Exception as e:
                    replay_job.failed_events += 1
                    error_msg = str(e)
                    replay_job.errors.append({
                        "event_id": event_id_str,
                        "error": error_msg,
                    })
                    _logger.error(f"Failed to replay embedding for event {event_id_str}: {error_msg}")
            
            offset += batch_size
            
            # 提交事务以释放资源
            session.commit()
        
        # 3. 作业完成，清理检查点
        cleanup_batch_checkpoint(session, replay_job.job_id)
        
        # 4. 记录审计日志
        audit_log(
            event="embedding.replay.complete",
            outcome="success" if replay_job.failed_events == 0 else "partial",
            details={
                "job_id": replay_job.job_id,
                "time_range_start": time_range_start,
                "time_range_end": time_range_end,
                "event_ids_count": len(event_ids) if event_ids else 0,
                "only_failed": only_failed,
                "total_events": replay_job.total_events,
                "processed_events": replay_job.processed_events,
                "succeeded_events": replay_job.succeeded_events,
                "failed_events": replay_job.failed_events,
                "resumed_from_checkpoint": checkpoint is not None,
                "errors_sample": replay_job.errors[:5],  # 记录前 5 个错误样本
            }
        )
        
        _logger.info(
            f"Replay completed: total={replay_job.total_events}, "
            f"succeeded={replay_job.succeeded_events}, failed={replay_job.failed_events}"
        )
        
        return {
            "job_id": replay_job.job_id,
            "status": "succeeded" if replay_job.failed_events == 0 else "partial",
            "total_events": replay_job.total_events,
            "processed_events": replay_job.processed_events,
            "succeeded_events": replay_job.succeeded_events,
            "failed_events": replay_job.failed_events,
            "resumed_from_checkpoint": checkpoint is not None,
            "errors": replay_job.errors[:10],  # 返回前 10 个错误
        }
        
    except Exception as e:
        error_msg = f"Replay batch job failed: {str(e)}"
        _logger.error(error_msg)
        
        # 发生异常时保存进度，支持断点续传
        persist_batch_progress(
            session=session,
            job_id=replay_job.job_id,
            total_events=replay_job.total_events,
            processed_events=replay_job.processed_events,
            succeeded_events=replay_job.succeeded_events,
            failed_events=replay_job.failed_events,
            last_processed_event_id=last_event_id if 'last_event_id' in dir() else None,
            status="interrupted",
            errors=replay_job.errors,
        )
        
        # 记录审计日志（失败）
        audit_log(
            event="embedding.replay.failed",
            outcome="fail",
            details={
                "job_id": replay_job.job_id,
                "error": error_msg,
                "time_range_start": time_range_start,
                "time_range_end": time_range_end,
            }
        )
        
        raise AppError(
            code=ErrorCode.EMBEDDINGS_UNAVAILABLE,
            message=error_msg,
            status_code=500
        ) from e
    finally:
        session.close()


def enqueue_replay_embeddings(
    time_range_start: datetime | None = None,
    time_range_end: datetime | None = None,
    event_ids: list[str] | None = None,
    only_failed: bool = True,
    priority: TaskPriority = TaskPriority.LOW,  # 重跑作业优先级较低
) -> Any:
    """
    将 embedding 批量重跑作业入队
    
    Args:
        time_range_start: 时间范围开始
        time_range_end: 时间范围结束
        event_ids: 指定的事件ID列表
        only_failed: 是否只重跑失败的
        priority: 任务优先级
        
    Returns:
        RQ Job 实例
    """
    start_str = time_range_start.isoformat() if time_range_start else None
    end_str = time_range_end.isoformat() if time_range_end else None
    
    return enqueue_task(
        replay_embeddings_batch,
        start_str,
        end_str,
        event_ids,
        only_failed,
        batch_size=100,
        queue_name=QUEUE_DEFAULT,
        priority=priority,
        timeout=3600,  # 1 小时
        job_meta={"task_type": "replay_embeddings", "only_failed": only_failed}
    )


def get_failed_embedding_events(
    time_range_start: datetime | None = None,
    time_range_end: datetime | None = None,
    limit: int = 100
) -> list[dict[str, Any]]:
    """
    获取需要重跑的 embedding 失败事件列表
    
    Args:
        time_range_start: 时间范围开始
        time_range_end: 时间范围结束
        limit: 返回数量限制
        
    Returns:
        失败事件列表
    """
    db = get_database()
    session = db.get_session()
    
    try:
        query = session.query(RawEvent, Embedding).join(
            Embedding, RawEvent.id == Embedding.event_id
        ).filter(
            RawEvent.deleted_at.is_(None)
        ).filter(
            (Embedding.error_message.isnot(None)) |
            (Embedding.embedding.is_(None))
        )
        
        if time_range_start:
            query = query.filter(RawEvent.occurred_at >= time_range_start)
        if time_range_end:
            query = query.filter(RawEvent.occurred_at <= time_range_end)
        
        results = query.limit(limit).all()
        
        return [
            {
                "event_id": str(raw.id),
                "content_preview": raw.content[:100] if raw.content else "",
                "occurred_at": raw.occurred_at.isoformat() if raw.occurred_at else None,
                "error_message": emb.error_message,
                "rerun_count": emb.rerun_count,
            }
            for raw, emb in results
        ]
    finally:
        session.close()


def get_embedding_stats() -> dict[str, Any]:
    """
    获取 embedding 统计信息
    
    Returns:
        统计信息字典
    """
    db = get_database()
    session = db.get_session()
    
    try:
        # 总事件数
        total_events = session.query(RawEvent).filter(
            RawEvent.deleted_at.is_(None)
        ).count()
        
        # 有 embedding 的事件数
        with_embedding = session.query(Embedding).filter(
            Embedding.embedding.isnot(None)
        ).count()
        
        # 失败的 embedding 数
        failed = session.query(Embedding).filter(
            (Embedding.error_message.isnot(None)) |
            (Embedding.embedding.is_(None))
        ).count()
        
        # 按模型的分布
        from sqlalchemy import func
        model_dist = session.query(
            Embedding.model_name,
            func.count(Embedding.id)
        ).filter(
            Embedding.embedding.isnot(None)
        ).group_by(Embedding.model_name).all()
        
        return {
            "total_events": total_events,
            "with_embedding": with_embedding,
            "failed": failed,
            "coverage_rate": with_embedding / total_events if total_events > 0 else 0,
            "model_distribution": {
                model: count for model, count in model_dist
            },
        }
    finally:
        session.close()
