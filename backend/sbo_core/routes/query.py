from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter

from sbo_core.query_service import query_service
from sbo_core.models import (
    QueryRequest,
    QueryResponse,
    MemoriesRequest,
    MemoriesResponse,
    ConversationMessagesRequest,
    ConversationMessagesResponse,
    MemoryType,
    TimeRange,
)
from sbo_core.errors import AppError, ErrorCode, query_failed

_logger = logging.getLogger("sbo_core")
router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_retrieval(request: QueryRequest) -> QueryResponse:
    """
    智能查询接口
    
    该接口用于执行智能查询检索，支持 fast 和 deep 两种模式：
    
    Fast 模式：
    - 仅使用语义记忆进行检索
    - 响应时间 < 500ms
    - 适用于一般性查询
    
    Deep 模式：
    - 并发检索语义记忆 + Episodic 记忆（WeKnora）
    - 支持时间衰减重排
    - 响应时间 < 2s
    - 适用于需要深度回忆的查询
    
    处理流程：
    1. 根据模式选择检索策略
    2. 执行多路召回（语义/Episodic/图谱）
    3. 融合和重排结果
    4. 过滤低质量证据
    5. 生成答案提示
    6. 返回证据列表和处理信息
    
    性能要求：
    - Fast 模式：< 500ms
    - Deep 模式：< 2s
    """
    try:
        _logger.info(f"Processing query: {request.query[:100]}... (mode: {request.mode})")
        
        # 执行查询检索
        response = await query_service.query(request)
        
        _logger.info(
            f"Query completed: {len(response.evidence)} evidence, "
            f"{response.processing_time_ms}ms, "
            f"degraded: {response.degraded_services}"
        )
        
        return response
        
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in query_retrieval: {e}")
        raise query_failed("Unexpected error during query retrieval")


@router.get("/memories", response_model=MemoriesResponse)
async def get_memories(
    user_id: str | None = None,
    memory_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    start_time: str | None = None,
    end_time: str | None = None
) -> MemoriesResponse:
    """
    获取记忆列表
    
    该接口用于获取用户的记忆列表，供 Sidebar 展示：
    
    支持的过滤条件：
    - user_id: 用户ID过滤
    - memory_type: 记忆类型过滤（preference/fact/event）
    - time_range: 时间范围过滤
    - limit/offset: 分页参数
    
    返回数据：
    - 记忆列表（按时间倒序）
    - 总数量
    - 是否还有更多
    
    性能要求：< 300ms
    """
    try:
        # 构建请求对象
        request = MemoriesRequest(
            user_id=user_id,
            memory_type=MemoryType(memory_type) if memory_type else None,
            limit=min(limit, 100),  # 限制最大值
            offset=max(offset, 0),
            time_range=TimeRange(
                start=datetime.fromisoformat(start_time) if start_time else None,
                end=datetime.fromisoformat(end_time) if end_time else None
            ) if start_time or end_time else None
        )
        
        _logger.info(f"Getting memories: user_id={user_id}, type={memory_type}, limit={limit}")
        
        # 获取记忆列表
        response = await query_service.get_memories(request)
        
        _logger.info(f"Retrieved {len(response.memories)} memories")
        
        return response
        
    except ValueError as e:
        # 处理枚举值错误
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid parameter: {str(e)}",
            status_code=422
        )
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in get_memories: {e}")
        raise AppError(
            code=ErrorCode.QUERY_FAILED,
            message="Failed to get memories",
            status_code=500
        )


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    include_evidence: bool = True
) -> ConversationMessagesResponse:
    """
    获取对话历史
    
    该接口用于获取指定对话的消息历史，供 Chat 界面展示：
    
    参数说明：
    - conversation_id: 对话ID
    - limit: 返回消息数量（最大100）
    - offset: 分页偏移
    - include_evidence: 是否包含相关证据
    
    返回数据：
    - 消息列表（按序列号正序）
    - 总消息数
    - 是否还有更多
    
    性能要求：< 200ms
    """
    try:
        import uuid
        
        request = ConversationMessagesRequest(
            conversation_id=uuid.UUID(conversation_id),
            limit=min(limit, 100),  # 限制最大值
            offset=max(offset, 0),
            include_evidence=include_evidence
        )
        
        _logger.info(f"Getting conversation messages: {conversation_id}")
        
        # 获取对话消息
        response = await query_service.get_conversation_messages(request)
        
        _logger.info(f"Retrieved {len(response.messages)} messages")
        
        return response
        
    except ValueError as e:
        # 处理 UUID 格式错误
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid conversation ID: {str(e)}",
            status_code=422
        )
    except AppError:
        raise
    except Exception as e:
        _logger.exception(f"Unexpected error in get_conversation_messages: {e}")
        raise AppError(
            code=ErrorCode.QUERY_FAILED,
            message="Failed to get conversation messages",
            status_code=500
        )
