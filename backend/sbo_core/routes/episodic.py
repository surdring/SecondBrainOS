from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from sbo_core.audit import audit_log
from sbo_core.config import load_settings
from sbo_core.errors import AppError, ErrorCode, get_request_id, WeKnoraError
from sbo_core.models import (
    KnowledgeBaseRequest,
    KnowledgeBaseResponse,
    IngestionRequest,
    IngestionResponse,
    IngestionJobResponse,
)
from sbo_core.weknora_client import WeKnoraClient

_logger = logging.getLogger("sbo_core")
router = APIRouter(prefix="/api/v1/episodic", tags=["episodic"])


def _get_weknora_client() -> WeKnoraClient:
    """获取 WeKnoraClient 实例"""
    settings = load_settings()
    return WeKnoraClient(
        base_url=settings.weknora_base_url,
        api_key=settings.weknora_api_key,
        timeout_ms=settings.weknora_request_timeout_ms,
    )


@router.get("/knowledge-bases")
async def list_knowledge_bases(http_request: Request) -> dict[str, Any]:
    """
    获取 WeKnora KnowledgeBase 列表

    透传 WeKnora /knowledge-bases 接口，返回知识库列表。
    """
    try:
        client = _get_weknora_client()
        kb_list = await client.list_knowledge_bases(
            request_id=get_request_id(http_request)
        )
        audit_log(
            event="episodic.kb.list",
            outcome="success",
            request_id=get_request_id(http_request),
            details={"count": len(kb_list)},
        )
        return {"data": kb_list, "success": True}
    except WeKnoraError as e:
        audit_log(
            event="episodic.kb.list",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={"error_code": e.code.value, "message": e.message},
        )
        raise AppError(
            code=ErrorCode.KNOWLEDGE_BASE_FAILED,
            message=f"Failed to list knowledge bases: {e.message}",
            status_code=503,
        )
    except Exception as e:
        _logger.exception(f"Unexpected error in list_knowledge_bases: {e}")
        audit_log(
            event="episodic.kb.list",
            outcome="error",
            request_id=get_request_id(http_request),
        )
        raise AppError(
            code=ErrorCode.KNOWLEDGE_BASE_FAILED,
            message="Unexpected error when listing knowledge bases",
            status_code=503,
        )


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    request: KnowledgeBaseRequest,
    http_request: Request,
) -> KnowledgeBaseResponse:
    """
    创建 WeKnora KnowledgeBase

    透传 WeKnora POST /knowledge-bases 接口。
    """
    try:
        client = _get_weknora_client()
        result = await client.create_knowledge_base(
            name=request.name,
            description=request.description,
            request_id=get_request_id(http_request),
        )
        audit_log(
            event="episodic.kb.create",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "kb_id": result.get("id"),
                "name": request.name,
            },
        )
        return KnowledgeBaseResponse(
            kb_id=result.get("id"),
            name=result.get("name", request.name),
            description=result.get("description", request.description),
            tags=result.get("tags", []),
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
            metadata=result.get("metadata", {}),
        )
    except WeKnoraError as e:
        audit_log(
            event="episodic.kb.create",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={"error_code": e.code.value, "message": e.message, "name": request.name},
        )
        raise AppError(
            code=ErrorCode.KNOWLEDGE_BASE_FAILED,
            message=f"Failed to create knowledge base: {e.message}",
            status_code=503,
        )
    except Exception as e:
        _logger.exception(f"Unexpected error in create_knowledge_base: {e}")
        audit_log(
            event="episodic.kb.create",
            outcome="error",
            request_id=get_request_id(http_request),
            details={"name": request.name},
        )
        raise AppError(
            code=ErrorCode.KNOWLEDGE_BASE_FAILED,
            message="Unexpected error when creating knowledge base",
            status_code=503,
        )


@router.post("/ingestions", response_model=IngestionResponse)
async def create_ingestion(
    request: IngestionRequest,
    http_request: Request,
) -> IngestionResponse:
    """
    创建 WeKnora Ingestion Job

    透传 WeKnora POST /ingestions 接口，启动异步导入任务。
    """
    try:
        client = _get_weknora_client()
        result = await client.create_ingestion(
            kb_id=str(request.kb_id),
            source_type=request.source_type,
            source_payload=request.source_payload,
            request_id=get_request_id(http_request),
        )
        audit_log(
            event="episodic.ingestion.create",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "ingestion_job_id": result.get("id"),
                "kb_id": str(request.kb_id),
                "source_type": request.source_type,
            },
        )
        return IngestionResponse(
            ingestion_job_id=result.get("id"),
        )
    except WeKnoraError as e:
        audit_log(
            event="episodic.ingestion.create",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={
                "error_code": e.code.value,
                "message": e.message,
                "kb_id": str(request.kb_id),
                "source_type": request.source_type,
            },
        )
        raise AppError(
            code=ErrorCode.INGESTION_FAILED,
            message=f"Failed to create ingestion job: {e.message}",
            status_code=503,
        )
    except Exception as e:
        _logger.exception(f"Unexpected error in create_ingestion: {e}")
        audit_log(
            event="episodic.ingestion.create",
            outcome="error",
            request_id=get_request_id(http_request),
            details={"kb_id": str(request.kb_id), "source_type": request.source_type},
        )
        raise AppError(
            code=ErrorCode.INGESTION_FAILED,
            message="Unexpected error when creating ingestion job",
            status_code=503,
        )


@router.get("/ingestions/{ingestion_job_id}", response_model=IngestionJobResponse)
async def get_ingestion_status(
    ingestion_job_id: str,
    http_request: Request,
) -> IngestionJobResponse:
    """
    获取 WeKnora Ingestion Job 状态

    透传 WeKnora GET /ingestions/{id} 接口，查询导入任务状态。
    """
    try:
        client = _get_weknora_client()
        result = await client.get_ingestion(
            ingestion_job_id=ingestion_job_id,
            request_id=get_request_id(http_request),
        )
        audit_log(
            event="episodic.ingestion.status",
            outcome="success",
            request_id=get_request_id(http_request),
            details={
                "ingestion_job_id": ingestion_job_id,
                "status": result.get("status"),
            },
        )
        return IngestionJobResponse(
            ingestion_job_id=result.get("id"),
            kb_id=result.get("kb_id"),
            status=result.get("status", "unknown"),
            source_type=result.get("source_type", ""),
            created_at=result.get("created_at"),
            started_at=result.get("started_at"),
            completed_at=result.get("completed_at"),
            error_message=result.get("error_message"),
            processed_items=result.get("processed_items", 0),
            total_items=result.get("total_items"),
        )
    except WeKnoraError as e:
        if e.code == ErrorCode.WEKNORA_NOT_FOUND:
            audit_log(
                event="episodic.ingestion.status",
                outcome="fail",
                request_id=get_request_id(http_request),
                details={"ingestion_job_id": ingestion_job_id, "error": "not_found"},
            )
            raise AppError(
                code=ErrorCode.INGESTION_JOB_NOT_FOUND,
                message="Ingestion job not found",
                status_code=404,
            )
        audit_log(
            event="episodic.ingestion.status",
            outcome="fail",
            request_id=get_request_id(http_request),
            details={"ingestion_job_id": ingestion_job_id, "error_code": e.code.value},
        )
        raise AppError(
            code=ErrorCode.INGESTION_JOB_FAILED,
            message=f"Failed to get ingestion status: {e.message}",
            status_code=503,
        )
    except Exception as e:
        _logger.exception(f"Unexpected error in get_ingestion_status: {e}")
        audit_log(
            event="episodic.ingestion.status",
            outcome="error",
            request_id=get_request_id(http_request),
            details={"ingestion_job_id": ingestion_job_id},
        )
        raise AppError(
            code=ErrorCode.INGESTION_JOB_FAILED,
            message="Unexpected error when getting ingestion status",
            status_code=503,
        )
