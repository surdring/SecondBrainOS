from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class IngestRequest(BaseModel):
    """数据录入请求模型"""
    source: str = Field(..., description="来源渠道", examples=["webchat", "telegram", "whatsapp"])
    source_message_id: str | None = Field(None, description="来源消息ID")
    occurred_at: datetime = Field(..., description="发生时间")
    content: str = Field(..., description="原始内容", min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list, description="标签列表")
    idempotency_key: str | None = Field(None, description="幂等键")
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed_sources = ['webchat', 'telegram', 'whatsapp', 'api', 'upload']
        if v not in allowed_sources:
            raise ValueError(f"Source must be one of: {', '.join(allowed_sources)}")
        return v
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("Too many tags (max 20)")
        for tag in v:
            if not tag or len(tag) > 50:
                raise ValueError("Each tag must be non-empty and max 50 characters")
        return v


class IngestResponse(BaseModel):
    """数据录入响应模型"""
    event_id: UUID = Field(..., description="事件唯一标识")
    queued_jobs: list[str] = Field(..., description="已入队的巩固任务列表")


class ChatRequest(BaseModel):
    """对话请求模型"""
    content: str = Field(..., description="对话内容", min_length=1, max_length=10000)
    source: str = Field(default="webchat", description="来源渠道")
    source_message_id: str | None = Field(None, description="来源消息ID")
    idempotency_key: str | None = Field(None, description="幂等键")
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed_sources = ['webchat', 'telegram', 'whatsapp', 'api']
        if v not in allowed_sources:
            raise ValueError(f"Source must be one of: {', '.join(allowed_sources)}")
        return v


class Evidence(BaseModel):
    """证据模型"""
    evidence_id: str = Field(..., description="证据ID")
    type: str = Field(..., description="证据类型")
    text: str = Field(..., description="证据文本")
    occurred_at: datetime = Field(..., description="发生时间")
    source: str = Field(..., description="来源")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    refs: dict[str, Any] = Field(default_factory=dict, description="引用信息")
    scores: dict[str, float] = Field(default_factory=dict, description="评分详情")
    request_id: str | None = Field(None, description="请求ID")
    retrieval_trace: dict[str, Any] | None = Field(None, description="检索追踪信息")


class ChatResponse(BaseModel):
    """对话响应模型"""
    assistant_message: str = Field(..., description="助手回复")
    evidence: list[Evidence] = Field(default_factory=list, description="证据列表")
    conversation_id: UUID = Field(..., description="对话ID")


class UploadRequest(BaseModel):
    """文件上传请求模型"""
    source: str = Field(default="upload", description="来源渠道")
    source_message_id: str | None = Field(None, description="来源消息ID")
    idempotency_key: str | None = Field(None, description="幂等键")
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v != "upload":
            raise ValueError("Source must be 'upload' for file upload")
        return v


class FileMetadata(BaseModel):
    """文件元数据模型"""
    file_id: UUID = Field(..., description="文件唯一标识")
    filename: str = Field(..., description="文件名")
    content_type: str = Field(..., description="文件类型")
    size_bytes: int = Field(..., description="文件大小（字节）")
    uploaded_at: datetime = Field(..., description="上传时间")


class UploadResponse(BaseModel):
    """文件上传响应模型"""
    file_id: UUID = Field(..., description="文件唯一标识")
    event_id: UUID = Field(..., description="关联的事件ID")
    queued_jobs: list[str] = Field(..., description="已入队的处理任务列表")
    metadata: FileMetadata = Field(..., description="文件元数据")


class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str = Field(..., description="查询语句", min_length=1, max_length=1000)
    top_k: int = Field(default=8, description="返回结果数量", ge=1, le=50)
    time_range: dict[str, datetime] | None = Field(None, description="时间范围")
    mode: str = Field(default="fast", description="查询模式")
    
    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed_modes = ['fast', 'deep']
        if v not in allowed_modes:
            raise ValueError(f"Mode must be one of: {', '.join(allowed_modes)}")
        return v
    
    @field_validator('time_range')
    @classmethod
    def validate_time_range(cls, v: dict[str, datetime] | None) -> dict[str, datetime] | None:
        if v is None:
            return None
        
        if 'start' not in v or 'end' not in v:
            raise ValueError("Time range must include 'start' and 'end'")
        
        if v['start'] >= v['end']:
            raise ValueError("Time range start must be before end")
        
        return v


class QueryResponse(BaseModel):
    """查询响应模型"""
    answer_hint: str | None = Field(None, description="答案提示")
    evidence: list[Evidence] = Field(default_factory=list, description="证据列表")
    mode_used: str = Field(..., description="实际使用的查询模式")
    degradation_info: dict[str, Any] | None = Field(None, description="降级信息")


class Memory(BaseModel):
    """记忆模型"""
    id: UUID = Field(..., description="记忆ID")
    content: str = Field(..., description="记忆内容")
    type: str = Field(..., description="记忆类型", examples=["preference", "fact", "event"])
    timestamp: datetime = Field(..., description="时间戳")
    confidence: float | None = Field(None, description="置信度")
    source: str | None = Field(None, description="来源")


class Message(BaseModel):
    """消息模型"""
    id: UUID = Field(..., description="消息ID")
    role: str = Field(..., description="角色", examples=["user", "assistant", "system"])
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(..., description="时间戳")
    evidence: list[Evidence] = Field(default_factory=list, description="证据列表")


class ConversationsResponse(BaseModel):
    """对话列表响应模型"""
    conversations: list[dict[str, Any]] = Field(default_factory=list, description="对话列表")
    total: int = Field(..., description="总数")
    offset: int = Field(..., description="偏移量")
    limit: int = Field(..., description="限制数量")


class MessagesResponse(BaseModel):
    """消息列表响应模型"""
    messages: list[Message] = Field(default_factory=list, description="消息列表")
    conversation_id: UUID = Field(..., description="对话ID")
    total: int = Field(..., description="总数")
    offset: int = Field(..., description="偏移量")
    limit: int = Field(..., description="限制数量")


class ForgetRequest(BaseModel):
    """记忆擦除请求模型"""
    time_range: dict[str, datetime] | None = Field(None, description="时间范围")
    tags: list[str] = Field(default_factory=list, description="标签过滤")
    event_ids: list[UUID] = Field(default_factory=list, description="事件ID列表")
    
    @field_validator('time_range')
    @classmethod
    def validate_time_range(cls, v: dict[str, datetime] | None) -> dict[str, datetime] | None:
        if v is None:
            return None
        
        if 'start' not in v or 'end' not in v:
            raise ValueError("Time range must include 'start' and 'end'")
        
        if v['start'] >= v['end']:
            raise ValueError("Time range start must be before end")
        
        return v
    
    @field_validator('event_ids')
    @classmethod
    def validate_event_ids(cls, v: list[UUID]) -> list[UUID]:
        if len(v) > 1000:
            raise ValueError("Too many event IDs (max 1000)")
        return v


class EraseJobStatus(str, Enum):
    """擦除作业状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ForgetResponse(BaseModel):
    """记忆擦除响应模型"""
    erase_job_id: UUID = Field(..., description="擦除作业ID")


class EraseJobResponse(BaseModel):
    """擦除作业状态响应模型"""
    erase_job_id: UUID = Field(..., description="擦除作业ID")
    status: EraseJobStatus = Field(..., description="作业状态")
    created_at: datetime = Field(..., description="创建时间")
    started_at: datetime | None = Field(None, description="开始时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    affected_events: int = Field(..., description="影响的事件数量")
    error_message: str | None = Field(None, description="错误信息")


class UserProfile(BaseModel):
    """用户档案模型"""
    user_id: UUID = Field(..., description="用户ID")
    facts: dict[str, Any] = Field(default_factory=dict, description="事实信息")
    preferences: dict[str, Any] = Field(default_factory=dict, description="偏好信息")
    constraints: dict[str, Any] = Field(default_factory=dict, description="约束条件")
    version: int = Field(default=1, description="版本号")
    updated_at: datetime = Field(..., description="更新时间")


class ProfileUpdateRequest(BaseModel):
    """档案更新请求模型"""
    facts: dict[str, Any] | None = Field(None, description="事实信息")
    preferences: dict[str, Any] | None = Field(None, description="偏好信息")
    constraints: dict[str, Any] | None = Field(None, description="约束条件")


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description="整体状态", examples=["healthy", "degraded", "unhealthy"])
    timestamp: datetime = Field(..., description="检查时间")
    services: dict[str, dict[str, Any]] = Field(..., description="服务状态详情")
    metrics: dict[str, Any] = Field(default_factory=dict, description="系统指标")


class FeedbackRequest(BaseModel):
    """反馈纠错请求模型"""
    evidence_id: str = Field(..., description="证据ID")
    feedback_type: str = Field(..., description="反馈类型")
    user_correction: str | None = Field(None, description="用户纠正文本")
    session_id: UUID | None = Field(None, description="会话ID")
    query: str | None = Field(None, description="原查询")
    
    @field_validator('feedback_type')
    @classmethod
    def validate_feedback_type(cls, v: str) -> str:
        allowed_types = ['incorrect', 'outdated', 'incomplete']
        if v not in allowed_types:
            raise ValueError(f"Feedback type must be one of: {', '.join(allowed_types)}")
        return v


class FeedbackResponse(BaseModel):
    """反馈纠错响应模型"""
    feedback_id: UUID = Field(..., description="反馈ID")
    status: str = Field(..., description="处理状态")


class KnowledgeBaseRequest(BaseModel):
    """KnowledgeBase 创建请求模型"""
    name: str = Field(..., description="名称", min_length=1, max_length=100)
    description: str | None = Field(None, description="描述", max_length=500)
    tags: list[str] = Field(default_factory=list, description="标签列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeBaseResponse(BaseModel):
    """KnowledgeBase 响应模型"""
    kb_id: str = Field(..., description="KnowledgeBase ID")
    name: str = Field(..., description="名称")
    description: str | None = Field(None, description="描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    created_at: datetime | None = Field(None, description="创建时间")
    updated_at: datetime | None = Field(None, description="更新时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class IngestionRequest(BaseModel):
    """导入请求模型"""
    kb_id: UUID = Field(..., description="KnowledgeBase ID")
    source_type: str = Field(..., description="来源类型")
    source_payload: dict[str, Any] = Field(..., description="来源载荷")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    occurred_at: datetime | None = Field(None, description="发生时间")
    
    @field_validator('source_type')
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        allowed_types = ['file', 'url', 'conversation_summary']
        if v not in allowed_types:
            raise ValueError(f"Source type must be one of: {', '.join(allowed_types)}")
        return v


class IngestionResponse(BaseModel):
    """导入响应模型"""
    ingestion_job_id: str = Field(..., description="导入作业ID")


class IngestionJobStatus(str, Enum):
    """导入作业状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionJobResponse(BaseModel):
    """导入作业状态响应模型"""
    ingestion_job_id: str = Field(..., description="导入作业ID")
    kb_id: str = Field(..., description="KnowledgeBase ID")
    status: IngestionJobStatus = Field(..., description="作业状态")
    source_type: str = Field(..., description="来源类型")
    created_at: datetime | None = Field(None, description="创建时间")
    started_at: datetime | None = Field(None, description="开始时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    error_message: str | None = Field(None, description="错误信息")
    processed_items: int = Field(default=0, description="处理项目数")
    total_items: int | None = Field(None, description="总项目数")


# 查询检索相关模型

class TimeRange(BaseModel):
    """时间范围模型"""
    start: datetime | None = Field(None, description="开始时间")
    end: datetime | None = Field(None, description="结束时间")


class QueryMode(str, Enum):
    """查询模式"""
    FAST = "fast"
    DEEP = "deep"


class MemoryType(str, Enum):
    """记忆类型"""
    PREFERENCE = "preference"
    FACT = "fact"
    EVENT = "event"


class EvidenceType(str, Enum):
    """证据类型"""
    RAW_EVENT = "raw_event"
    PROFILE_FACT = "profile_fact"
    GRAPH_FACT = "graph_fact"


class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str = Field(..., min_length=1, max_length=1000, description="查询语句", examples=["我昨天说了什么？"])
    top_k: int = Field(default=5, ge=1, le=50, description="返回结果数量")
    time_range: TimeRange | None = Field(None, description="时间范围过滤")
    mode: QueryMode = Field(default=QueryMode.FAST, description="查询模式")
    user_id: str | None = Field(None, description="用户ID（可选）")
    conversation_id: UUID | None = Field(None, description="对话ID（可选）")


class QueryResponse(BaseModel):
    """查询响应模型"""
    answer_hint: str | None = Field(None, description="答案提示（可选）")
    evidence: list[Evidence] = Field(..., description="证据列表")
    query_mode: QueryMode = Field(..., description="实际使用的查询模式")
    total_candidates: int = Field(..., description="候选总数")
    processing_time_ms: int = Field(..., description="处理时间（毫秒）")
    degraded_services: list[str] = Field(default_factory=list, description="降级的服务列表")


class MemoriesRequest(BaseModel):
    """记忆列表请求模型"""
    user_id: str | None = Field(None, description="用户ID（可选）")
    memory_type: MemoryType | None = Field(None, description="记忆类型过滤")
    time_range: TimeRange | None = Field(None, description="时间范围过滤")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="分页偏移")


class MemoryItem(BaseModel):
    """记忆项模型"""
    memory_id: str = Field(..., description="记忆ID")
    type: MemoryType = Field(..., description="记忆类型")
    content: str = Field(..., description="记忆内容")
    timestamp: datetime = Field(..., description="时间戳")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    source_events: list[str] = Field(default_factory=list, description="来源事件列表")


class MemoriesResponse(BaseModel):
    """记忆列表响应模型"""
    memories: list[MemoryItem] = Field(..., description="记忆列表")
    total_count: int = Field(..., description="总数量")
    has_more: bool = Field(..., description="是否还有更多")


class ConversationMessagesRequest(BaseModel):
    """对话消息请求模型"""
    conversation_id: UUID = Field(..., description="对话ID")
    limit: int = Field(default=50, ge=1, le=100, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="分页偏移")
    include_evidence: bool = Field(default=True, description="是否包含证据")


class MessageItem(BaseModel):
    """消息项模型"""
    message_id: str = Field(..., description="消息ID")
    role: str = Field(..., description="角色（user/assistant/system）")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(..., description="时间戳")
    sequence_number: int = Field(..., description="序列号")
    evidence: list[Evidence] = Field(default_factory=list, description="相关证据")


class ConversationMessagesResponse(BaseModel):
    """对话消息响应模型"""
    conversation_id: UUID = Field(..., description="对话ID")
    messages: list[MessageItem] = Field(..., description="消息列表")
    total_count: int = Field(..., description="总消息数")
    has_more: bool = Field(..., description="是否还有更多")
