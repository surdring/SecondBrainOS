from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from sbo_core.services import event_service, conversation_service, file_service
from sbo_core.errors import (
    AppError,
    ErrorCode,
    validation_error,
    not_found_error,
    ingest_failed,
    upload_failed,
    chat_failed,
    duplicate_event,
)
from sbo_core.models import (
    IngestRequest,
    IngestResponse,
    ChatRequest,
    ChatResponse,
    UploadRequest,
    UploadResponse,
    FileMetadata,
    Evidence,
)

_logger = logging.getLogger("sbo_core")
router = APIRouter(prefix="/api/v1", tags=["ingest"])


async def _check_idempotency(idempotency_key: str | None) -> None:
    """检查幂等性"""
    # 幂等性检查现在在 event_service.create_raw_event 中进行
    pass


async def _write_raw_event(request: IngestRequest | ChatRequest, user_id: str | None = None) -> uuid.UUID:
    """写入原始事件到数据库"""
    return await event_service.create_raw_event(request, user_id)


async def _queue_consolidation_jobs(event_id: uuid.UUID, user_id: str | None = None) -> list[str]:
    """将巩固任务入队"""
    return await event_service.queue_consolidation_jobs(event_id, user_id)


@router.post("/ingest", response_model=IngestResponse)
async def ingest_event(request: IngestRequest) -> IngestResponse:
    """
    录入原始事件数据
    
    该接口用于录入各种来源的原始事件数据，包括：
    - 用户输入的文本内容
    - 系统生成的日志
    - 其他渠道转发的内容
    
    处理流程：
    1. 检查幂等性（如果提供了 idempotency_key）
    2. 写入 raw_events 表（事实源）
    3. 将巩固任务入队（异步处理）
    4. 返回快速确认
    
    性能要求：响应时间 < 1 秒
    """
    try:
        # 1. 检查幂等性
        await _check_idempotency(request.idempotency_key)
        
        # 2. 写入原始事件（必须先落库）
        event_id = await _write_raw_event(request)
        
        # 3. 将巩固任务入队（异步处理）
        queued_jobs = await _queue_consolidation_jobs(event_id)
        
        # 4. 返回快速确认
        _logger.info(f"Successfully ingested event {event_id}")
        
        return IngestResponse(
            event_id=event_id,
            queued_jobs=queued_jobs,
        )
        
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in ingest_event: {e}")
        raise ingest_failed("Unexpected error during event ingestion")


@router.post("/chat", response_model=ChatResponse)
async def chat_interaction(request: ChatRequest) -> ChatResponse:
    """
    对话式交互接口
    
    该接口用于处理用户对话交互，包括：
    - 接收用户消息
    - 自动召回相关证据（fast 模式）
    - 调用模型生成回复
    - 返回助手回复和证据
    
    处理流程：
    1. 写入用户消息到 raw_events
    2. 执行 fast 模式检索
    3. 调用 LLM 生成回复
    4. 写入助手回复到 raw_events
    5. 将巩固任务入队
    6. 返回回复和证据
    
    性能要求：响应时间 < 1.5 秒
    """
    try:
        user_id = "default_user"  # TODO: 从认证信息中获取真实用户ID
        
        # 1. 检查幂等性
        await _check_idempotency(request.idempotency_key)
        
        # 2. 写入用户消息到 raw_events
        user_event_id = await _write_raw_event(request, user_id)
        
        # 3. 执行 fast 模式检索（TODO: 实现检索逻辑）
        evidence = []
        try:
            # TODO: 实现检索逻辑
            _logger.info(f"Retrieving evidence for user event {user_event_id}")
            # 这里会调用检索模块
        except Exception as e:
            _logger.warning(f"Failed to retrieve evidence: {e}")
            # 检索失败不应该阻止对话
        
        # 4. 调用 LLM 生成回复（TODO: 实现 LLM 调用）
        assistant_message = "I'm sorry, I'm not fully configured yet. This is a placeholder response."
        try:
            # TODO: 实现 LLM 调用逻辑
            _logger.info(f"Generating assistant response for user event {user_event_id}")
        except Exception as e:
            _logger.warning(f"Failed to generate LLM response: {e}")
            # LLM 失败时使用默认响应
        
        # 5. 创建或获取对话
        conversation_id = await conversation_service.create_conversation(user_id)
        
        # 6. 写入助手回复到 raw_events
        assistant_event_id = uuid.uuid4()
        
        # 创建助手回复事件
        class AssistantEventRequest:
            def __init__(self):
                self.source = request.source
                self.source_message_id = request.source_message_id
                self.occurred_at = datetime.now(timezone.utc)
                self.content = assistant_message
                self.tags = ["assistant_reply"]
                self.idempotency_key = request.idempotency_key
        
        await _write_raw_event(AssistantEventRequest(), user_id)
        _logger.info(f"Writing assistant response {assistant_event_id} to database")
        
        # 7. 添加消息到对话
        await conversation_service.add_message_to_conversation(
            conversation_id, user_event_id, "user", request.content
        )
        await conversation_service.add_message_to_conversation(
            conversation_id, assistant_event_id, "assistant", assistant_message
        )
        
        # 8. 将巩固任务入队
        queued_jobs = await _queue_consolidation_jobs(user_event_id, user_id)
        queued_jobs.extend(await _queue_consolidation_jobs(assistant_event_id, user_id))
        
        _logger.info(f"Successfully processed chat interaction {user_event_id}")
        
        return ChatResponse(
            assistant_message=assistant_message,
            evidence=evidence,
            conversation_id=conversation_id,
        )
        
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in chat_interaction: {e}")
        raise chat_failed("Unexpected error during chat interaction")


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    source: str = Form(default="upload"),
    source_message_id: str | None = Form(None),
    idempotency_key: str | None = Form(None),
) -> UploadResponse:
    """
    文件上传接口
    
    该接口用于上传文件并进行处理，包括：
    - 接收文件上传
    - 生成文件元数据
    - 将文件处理任务入队
    - 返回文件信息和事件ID
    
    支持的文件格式：
    - JPG、PNG、WebP（图片）
    - TXT、MD（文本）
    - PDF（文档）
    
    处理流程：
    1. 验证文件格式和大小
    2. 保存文件到存储
    3. 生成文件元数据
    4. 写入上传事件到 raw_events
    5. 将文件处理任务入队（OCR、抽取等）
    6. 返回文件信息
    
    性能要求：文件上传 < 10 秒
    """
    try:
        user_id = "default_user"  # TODO: 从认证信息中获取真实用户ID
        
        # 1. 验证文件格式和大小
        allowed_content_types = [
            "image/jpeg",
            "image/png", 
            "image/webp",
            "text/plain",
            "text/markdown",
            "application/pdf",
        ]
        
        if file.content_type not in allowed_content_types:
            raise upload_failed(f"Unsupported file type: {file.content_type}")
        
        max_file_size = 50 * 1024 * 1024  # 50MB
        file_size = 0
        content = b""
        
        # 读取文件内容并检查大小
        while chunk := await file.read(8192):
            file_size += len(chunk)
            if file_size > max_file_size:
                raise upload_failed("File too large (max 50MB)")
            content += chunk
        
        await file.seek(0)  # 重置文件指针
        
        # 2. 保存文件到存储（TODO: 实现文件存储）
        file_id = uuid.uuid4()
        storage_path = f"uploads/{file_id}/{file.filename}"
        _logger.info(f"Saving file {file_id} with size {file_size} bytes to {storage_path}")
        
        # 3. 保存文件元数据到数据库
        await file_service.save_file_metadata(
            file_id=file_id,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            size_bytes=file_size,
            storage_path=storage_path,
            user_id=user_id
        )
        
        # 4. 生成文件元数据
        metadata = FileMetadata(
            file_id=file_id,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            size_bytes=file_size,
            uploaded_at=datetime.now(timezone.utc),
        )
        
        # 5. 创建上传请求并写入事件
        upload_request = UploadRequest(
            source=source,
            source_message_id=source_message_id,
            idempotency_key=idempotency_key,
        )
        
        # 创建事件内容
        event_content = f"Uploaded file: {metadata.filename} ({metadata.content_type}, {metadata.size_bytes} bytes)"
        
        # 创建一个类似 IngestRequest 的对象用于写入
        class UploadEventRequest:
            def __init__(self):
                self.source = upload_request.source
                self.source_message_id = upload_request.source_message_id
                self.occurred_at = datetime.now(timezone.utc)
                self.content = event_content
                self.tags = ["upload", metadata.content_type]
                self.idempotency_key = upload_request.idempotency_key
        
        event_id = await _write_raw_event(UploadEventRequest(), user_id)
        
        # 6. 将文件处理任务入队（TODO: 实现文件处理）
        processing_jobs = []
        job_types = []
        
        if metadata.content_type.startswith("image/"):
            job_types.extend(["ocr_extract", "image_analyze"])
        elif metadata.content_type == "application/pdf":
            job_types.extend(["pdf_extract", "document_analyze"])
        elif metadata.content_type.startswith("text/"):
            job_types.extend(["text_extract", "document_analyze"])
        
        for job_type in job_types:
            try:
                job_id = f"{job_type}:{file_id}"
                processing_jobs.append(job_id)
                _logger.info(f"Queueing {job_type} for file {file_id}")
            except Exception as e:
                _logger.warning(f"Failed to queue {job_type}: {e}")
        
        # 7. 合并所有任务
        all_jobs = await _queue_consolidation_jobs(event_id, user_id)
        all_jobs.extend(processing_jobs)
        
        _logger.info(f"Successfully uploaded file {file_id}")
        
        return UploadResponse(
            file_id=file_id,
            event_id=event_id,
            queued_jobs=all_jobs,
            metadata=metadata,
        )
        
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in upload_file: {e}")
        raise upload_failed("Unexpected error during file upload")
