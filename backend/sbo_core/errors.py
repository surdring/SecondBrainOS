from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """全局错误码枚举"""
    
    # 通用错误 (1000-1999)
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"
    HTTP_ERROR = "http_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    RATE_LIMITED = "rate_limited"
    
    # 参数校验错误 (2000-2999)
    INVALID_QUERY = "invalid_query"
    INVALID_TIME_RANGE = "invalid_time_range"
    INVALID_MODE = "invalid_mode"
    INVALID_TOP_K = "invalid_top_k"
    INVALID_SOURCE = "invalid_source"
    INVALID_CONTENT = "invalid_content"
    INVALID_TAGS = "invalid_tags"
    INVALID_IDEMPOTENCY_KEY = "invalid_idempotency_key"
    
    # 数据录入错误 (3000-3999)
    INGEST_FAILED = "ingest_failed"
    UPLOAD_FAILED = "upload_failed"
    CHAT_FAILED = "chat_failed"
    DUPLICATE_EVENT = "duplicate_event"
    
    # 查询检索错误 (4000-4999)
    QUERY_FAILED = "query_failed"
    RETRIEVAL_FAILED = "retrieval_failed"
    EVIDENCE_NOT_FOUND = "evidence_not_found"
    MEMORY_NOT_FOUND = "memory_not_found"
    FILTER_FAILED = "filter_failed"
    RERANK_FAILED = "rerank_failed"
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    
    # 外部依赖错误 (5000-5999)
    WEKNORA_UNAVAILABLE = "weknora_unavailable"
    WEKNORA_TIMEOUT = "weknora_timeout"
    WEKNORA_AUTH_FAILED = "weknora_auth_failed"
    WEKNORA_NOT_FOUND = "weknora_not_found"
    WEKNORA_RATE_LIMITED = "weknora_rate_limited"
    WEKNORA_INVALID_RESPONSE = "weknora_invalid_response"
    
    EMBEDDINGS_UNAVAILABLE = "embeddings_unavailable"
    EMBEDDINGS_TIMEOUT = "embeddings_timeout"
    EMBEDDINGS_AUTH_FAILED = "embeddings_auth_failed"
    EMBEDDINGS_RATE_LIMITED = "embeddings_rate_limited"
    
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_TIMEOUT = "llm_timeout"
    LLM_AUTH_FAILED = "llm_auth_failed"
    LLM_RATE_LIMITED = "llm_rate_limited"
    
    POSTGRES_UNAVAILABLE = "postgres_unavailable"
    REDIS_UNAVAILABLE = "redis_unavailable"
    NEO4J_UNAVAILABLE = "neo4j_unavailable"
    
    # 管理接口错误 (6000-6999)
    FORGET_FAILED = "forget_failed"
    ERASE_JOB_NOT_FOUND = "erase_job_not_found"
    ERASE_JOB_FAILED = "erase_job_failed"
    PROFILE_UPDATE_FAILED = "profile_update_failed"
    PROFILE_NOT_FOUND = "profile_not_found"
    
    # 巩固任务错误 (6100-6199)
    CONSOLIDATION_FAILED = "consolidation_failed"
    EVENT_NOT_FOUND = "event_not_found"
    EXTRACTION_NOT_FOUND = "extraction_not_found"
    
    # Episodic 管理错误 (7000-7999)
    KNOWLEDGE_BASE_FAILED = "knowledge_base_failed"
    KNOWLEDGE_BASE_NOT_FOUND = "knowledge_base_not_found"
    INGESTION_FAILED = "ingestion_failed"
    INGESTION_JOB_NOT_FOUND = "ingestion_job_not_found"
    INGESTION_JOB_FAILED = "ingestion_job_failed"
    
    # 反馈纠错错误 (8000-8999)
    FEEDBACK_FAILED = "feedback_failed"
    EVIDENCE_FEEDBACK_INVALID = "evidence_feedback_invalid"
    FEEDBACK_TYPE_INVALID = "feedback_type_invalid"
    
    # 配置错误 (9000-9999)
    CONFIG_MISSING = "config_missing"
    CONFIG_INVALID = "config_invalid"


class ErrorResponse(BaseModel):
    """统一错误响应模型"""
    code: ErrorCode
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class AppError(Exception):
    """应用自定义错误"""
    
    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ExternalDependencyError(AppError):
    """外部依赖错误基类"""
    
    def __init__(
        self,
        *,
        service: str,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        code = ErrorCode(f"{service}_{error_type}")
        super().__init__(code=code, message=message, status_code=503, details=details)


class WeKnoraError(ExternalDependencyError):
    """WeKnora 相关错误"""
    
    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(service="weknora", error_type=error_type, message=message, details=details)


class EmbeddingsError(ExternalDependencyError):
    """Embeddings 相关错误"""
    
    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(service="embeddings", error_type=error_type, message=message, details=details)


class LLMError(ExternalDependencyError):
    """LLM 相关错误"""
    
    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(service="llm", error_type=error_type, message=message, details=details)


class DatabaseError(ExternalDependencyError):
    """数据库相关错误"""
    
    def __init__(self, database: str, error_type: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(service=database, error_type=error_type, message=message, details=details)


def get_request_id(request: Request) -> str | None:
    """获取请求 ID"""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return None


def create_error_response(
    request: Request,
    code: ErrorCode,
    message: str,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    """创建错误响应"""
    return ErrorResponse(
        code=code,
        message=message,
        request_id=get_request_id(request),
        details=details,
    )


# 常用错误创建函数
def validation_error(message: str = "Request validation failed") -> AppError:
    """参数校验错误"""
    return AppError(code=ErrorCode.VALIDATION_ERROR, message=message, status_code=422)


def unauthorized_error(message: str = "Unauthorized") -> AppError:
    """未授权错误"""
    return AppError(code=ErrorCode.UNAUTHORIZED, message=message, status_code=401)


def forbidden_error(message: str = "Forbidden") -> AppError:
    """禁止访问错误"""
    return AppError(code=ErrorCode.FORBIDDEN, message=message, status_code=403)


def not_found_error(resource: str, identifier: str | None = None) -> AppError:
    """资源未找到错误"""
    message = f"{resource} not found"
    if identifier:
        message += f": {identifier}"
    return AppError(code=ErrorCode.NOT_FOUND, message=message, status_code=404)


def internal_error(message: str = "Internal server error") -> AppError:
    """内部服务器错误"""
    return AppError(code=ErrorCode.INTERNAL_ERROR, message=message, status_code=500)


def weknora_unavailable_error(details: dict[str, Any] | None = None) -> WeKnoraError:
    """WeKnora 不可用错误"""
    return WeKnoraError(
        error_type="unavailable",
        message="WeKnora service is unavailable",
        details=details,
    )


def weknora_timeout_error(details: dict[str, Any] | None = None) -> WeKnoraError:
    """WeKnora 超时错误"""
    return WeKnoraError(
        error_type="timeout",
        message="WeKnora service timeout",
        details=details,
    )


def weknora_auth_error(details: dict[str, Any] | None = None) -> WeKnoraError:
    """WeKnora 认证失败错误"""
    return WeKnoraError(
        error_type="auth_failed",
        message="WeKnora authentication failed",
        details=details,
    )


def embeddings_unavailable_error(details: dict[str, Any] | None = None) -> EmbeddingsError:
    """Embeddings 不可用错误"""
    return EmbeddingsError(
        error_type="unavailable",
        message="Embeddings service is unavailable",
        details=details,
    )


def llm_unavailable_error(details: dict[str, Any] | None = None) -> LLMError:
    """LLM 不可用错误"""
    return LLMError(
        error_type="unavailable",
        message="LLM service is unavailable",
        details=details,
    )


def postgres_unavailable_error(details: dict[str, Any] | None = None) -> DatabaseError:
    """PostgreSQL 不可用错误"""
    return DatabaseError(
        database="postgres",
        error_type="unavailable",
        message="PostgreSQL is unavailable",
        details=details,
    )


def redis_unavailable_error(details: dict[str, Any] | None = None) -> DatabaseError:
    """Redis 不可用错误"""
    return DatabaseError(
        database="redis",
        error_type="unavailable",
        message="Redis is unavailable",
        details=details,
    )


def neo4j_unavailable_error(details: dict[str, Any] | None = None) -> DatabaseError:
    """Neo4j 不可用错误"""
    return DatabaseError(
        database="neo4j",
        error_type="unavailable",
        message="Neo4j is unavailable",
        details=details,
    )


def config_missing_error(config_name: str) -> AppError:
    """配置缺失错误"""
    return AppError(
        code=ErrorCode.CONFIG_MISSING,
        message=f"Missing required configuration: {config_name}",
        status_code=500,
    )


def config_invalid_error(config_name: str, reason: str) -> AppError:
    """配置无效错误"""
    return AppError(
        code=ErrorCode.CONFIG_INVALID,
        message=f"Invalid configuration {config_name}: {reason}",
        status_code=500,
    )


def ingest_failed(message: str = "Ingest failed") -> AppError:
    """数据录入失败错误"""
    return AppError(code=ErrorCode.INGEST_FAILED, message=message, status_code=503)


def upload_failed(message: str = "Upload failed") -> AppError:
    """文件上传失败错误"""
    return AppError(code=ErrorCode.UPLOAD_FAILED, message=message, status_code=503)


def chat_failed(message: str = "Chat failed") -> AppError:
    """对话失败错误"""
    return AppError(code=ErrorCode.CHAT_FAILED, message=message, status_code=503)


def duplicate_event(message: str = "Duplicate event") -> AppError:
    """重复事件错误"""
    return AppError(code=ErrorCode.DUPLICATE_EVENT, message=message, status_code=409)


def query_failed(message: str = "Query failed") -> AppError:
    """查询失败错误"""
    return AppError(code=ErrorCode.QUERY_FAILED, message=message, status_code=500)


def retrieval_failed(message: str = "Retrieval failed") -> AppError:
    """检索失败错误"""
    return AppError(code=ErrorCode.RETRIEVAL_FAILED, message=message, status_code=500)


def evidence_not_found(message: str = "Evidence not found") -> AppError:
    """证据未找到错误"""
    return AppError(code=ErrorCode.EVIDENCE_NOT_FOUND, message=message, status_code=404)


def memory_not_found(message: str = "Memory not found") -> AppError:
    """记忆未找到错误"""
    return AppError(code=ErrorCode.MEMORY_NOT_FOUND, message=message, status_code=404)


def conversation_not_found(message: str = "Conversation not found") -> AppError:
    """对话未找到错误"""
    return AppError(code=ErrorCode.CONVERSATION_NOT_FOUND, message=message, status_code=404)


def rerank_failed(message: str = "Rerank failed") -> AppError:
    """重排失败错误"""
    return AppError(code=ErrorCode.RERANK_FAILED, message=message, status_code=500)
