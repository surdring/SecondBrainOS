from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sbo_core.database import get_database, RawEvent, Conversation, Message, EvidenceFeedback
from sbo_core.errors import AppError, ErrorCode, query_failed
from sbo_core.services import evidence_access_service
from sbo_core.models import (
    QueryRequest,
    QueryResponse,
    QueryMode,
    Evidence,
    EvidenceType,
    MemoriesRequest,
    MemoriesResponse,
    MemoryItem,
    MemoryType,
    ConversationMessagesRequest,
    ConversationMessagesResponse,
    MessageItem,
)
from sbo_core.retrieval_pipeline import retrieval_pipeline


class QueryService:
    """查询检索服务"""
    
    def __init__(self):
        self.db = None
        self._query_cache: dict[tuple[str, str], tuple[float, list[Evidence], list[str]]] = {}
        self._query_cache_ttl_seconds = 10.0
        self._query_cache_max_entries = 128
        self._min_evidence_confidence = 0.3
        self._max_evidence_items = 8
    
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.strip().lower().split())

    def _cache_key(self, conversation_id: UUID, query: str) -> tuple[str, str]:
        return (str(conversation_id), self._normalize_query(query))

    def _cache_get(self, conversation_id: UUID, query: str) -> tuple[list[Evidence], list[str]] | None:
        key = self._cache_key(conversation_id, query)
        item = self._query_cache.get(key)
        if not item:
            return None
        ts, evidence, degraded = item
        if (time.time() - ts) > self._query_cache_ttl_seconds:
            self._query_cache.pop(key, None)
            return None
        return evidence, degraded

    def _cache_set(self, conversation_id: UUID, query: str, evidence: list[Evidence], degraded: list[str]) -> None:
        if len(self._query_cache) >= self._query_cache_max_entries:
            oldest_key: tuple[str, str] | None = None
            oldest_ts = float("inf")
            for k, (ts, _, _) in self._query_cache.items():
                if ts < oldest_ts:
                    oldest_ts = ts
                    oldest_key = k
            if oldest_key is not None:
                self._query_cache.pop(oldest_key, None)

        key = self._cache_key(conversation_id, query)
        self._query_cache[key] = (time.time(), evidence, degraded)

    def _apply_evidence_guardrails(self, evidence: list[Evidence]) -> list[Evidence]:
        filtered = [e for e in evidence if (e.confidence or 0.0) >= self._min_evidence_confidence]
        return filtered[: self._max_evidence_items]

    def _get_filtered_evidence_ids(self, user_id: str | None) -> set[str]:
        """获取被用户标记为 incorrect/outdated 的证据 ID 集合"""
        if user_id is None:
            return set()
        db = self._get_db()
        session = db.get_session()
        try:
            rows = (
                session.query(EvidenceFeedback.evidence_id)
                .filter(
                    EvidenceFeedback.user_id == user_id,
                    EvidenceFeedback.feedback_type.in_(["incorrect", "outdated"])
                )
                .distinct()
                .all()
            )
            return {r.evidence_id for r in rows}
        except Exception:
            return set()
        finally:
            session.close()

    def _apply_feedback_filter(self, evidence: list[Evidence], user_id: str | None) -> list[Evidence]:
        """应用反馈过滤：移除被标记为 incorrect/outdated 的证据"""
        filtered_ids = self._get_filtered_evidence_ids(user_id)
        if not filtered_ids:
            return evidence
        return [e for e in evidence if e.evidence_id not in filtered_ids]
    
    async def query(self, request: QueryRequest) -> QueryResponse:
        """执行查询检索"""
        start_time = time.time()
        degraded_services = []
        
        try:
            if request.conversation_id is not None:
                cached = self._cache_get(request.conversation_id, request.query)
                if cached is not None:
                    cached_evidence, cached_degraded = cached
                    processing_time = int((time.time() - start_time) * 1000)
                    return QueryResponse(
                        answer_hint=await self._generate_answer_hint(request.query, cached_evidence),
                        evidence=cached_evidence,
                        query_mode=request.mode,
                        total_candidates=len(cached_evidence),
                        processing_time_ms=processing_time,
                        degraded_services=list(cached_degraded),
                    )

            # 使用检索管线处理查询
            time_range = None
            if request.time_range:
                time_range = (request.time_range.start, request.time_range.end)

            top_k = min(request.top_k, self._max_evidence_items)
            
            evidence_list, pipeline_degraded = await retrieval_pipeline.process(
                query=request.query,
                top_k=top_k,
                mode=request.mode.value,
                time_range=time_range,
                user_id=request.user_id
            )
            
            # 合并降级服务列表
            degraded_services.extend(pipeline_degraded)

            evidence_list = self._apply_evidence_guardrails(evidence_list)
            evidence_list = self._apply_feedback_filter(evidence_list, request.user_id)

            if request.user_id:
                evidence_ids = [e.evidence_id for e in evidence_list if e.evidence_id]
                if evidence_ids:
                    asyncio.create_task(
                        evidence_access_service.record_access(
                            user_id=request.user_id,
                            evidence_ids=evidence_ids,
                            accessed_at=datetime.now(timezone.utc),
                        )
                    )

            if request.conversation_id is not None:
                self._cache_set(request.conversation_id, request.query, evidence_list, degraded_services)
            
            # 生成答案提示（可选）
            answer_hint = await self._generate_answer_hint(request.query, evidence_list)
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return QueryResponse(
                answer_hint=answer_hint,
                evidence=evidence_list,
                query_mode=request.mode,
                total_candidates=len(evidence_list),
                processing_time_ms=processing_time,
                degraded_services=degraded_services
            )
            
        except Exception as e:
            if isinstance(e, AppError):
                raise
            raise query_failed(f"Query failed: {str(e)}")
    
    async def _generate_answer_hint(self, query: str, evidence: list[Evidence]) -> str | None:
        """生成答案提示"""
        if not evidence:
            return None
        
        # 简单的答案提示生成
        # TODO: 使用 LLM 生成更智能的答案提示
        top_evidence = evidence[:3]
        evidence_texts = [e.text for e in top_evidence]
        
        return f"Based on the following information: {'; '.join(evidence_texts[:2])}"
    
    async def get_memories(self, request: MemoriesRequest) -> MemoriesResponse:
        """获取记忆列表"""
        try:
            db = self._get_db()
            session = db.get_session()
            
            # TODO: 实现从结构化记忆表查询
            # 这里先从 raw_events 模拟
            query = session.query(RawEvent)
            
            # 应用过滤条件
            if request.user_id:
                query = query.filter(RawEvent.user_id == request.user_id)
            
            if request.time_range:
                if request.time_range.start:
                    query = query.filter(RawEvent.occurred_at >= request.time_range.start)
                if request.time_range.end:
                    query = query.filter(RawEvent.occurred_at <= request.time_range.end)
            
            # 计算总数
            total_count = query.count()
            
            # 应用分页
            memories = query.order_by(RawEvent.occurred_at.desc()).offset(request.offset).limit(request.limit).all()
            
            memory_items = []
            for event in memories:
                memory_item = MemoryItem(
                    memory_id=event.id,
                    type=MemoryType.EVENT,  # 简化处理
                    content=event.content,
                    timestamp=event.occurred_at,
                    confidence=0.8,
                    source_events=[event.id]
                )
                memory_items.append(memory_item)
            
            has_more = (request.offset + len(memories)) < total_count
            
            return MemoriesResponse(
                memories=memory_items,
                total_count=total_count,
                has_more=has_more
            )
            
        except Exception as e:
            raise AppError(
                code=ErrorCode.QUERY_FAILED,
                message=f"Failed to get memories: {str(e)}",
                status_code=500
            )
        finally:
            if 'session' in locals():
                session.close()
    
    async def get_conversation_messages(self, request: ConversationMessagesRequest) -> ConversationMessagesResponse:
        """获取对话消息"""
        try:
            db = self._get_db()
            session = db.get_session()
            
            # 获取对话
            conversation = session.query(Conversation).filter(
                Conversation.id == request.conversation_id
            ).first()
            
            if not conversation:
                raise AppError(
                    code=ErrorCode.NOT_FOUND,
                    message="Conversation not found",
                    status_code=404
                )
            
            # 获取消息
            messages_query = session.query(Message).filter(
                Message.conversation_id == request.conversation_id
            )
            
            # 计算总数
            total_count = messages_query.count()
            
            # 应用分页
            messages = messages_query.order_by(Message.sequence_number.asc()).offset(request.offset).limit(request.limit).all()
            
            message_items = []
            for msg in messages:
                # 如果需要包含证据，这里可以添加
                evidence_list = []
                if request.include_evidence:
                    # TODO: 实现证据检索
                    pass
                
                message_item = MessageItem(
                    message_id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.created_at,
                    sequence_number=msg.sequence_number,
                    evidence=evidence_list
                )
                message_items.append(message_item)
            
            has_more = (request.offset + len(messages)) < total_count
            
            return ConversationMessagesResponse(
                conversation_id=request.conversation_id,
                messages=message_items,
                total_count=total_count,
                has_more=has_more
            )
            
        except AppError:
            raise
        except Exception as e:
            raise AppError(
                code=ErrorCode.QUERY_FAILED,
                message=f"Failed to get conversation messages: {str(e)}",
                status_code=500
            )
        finally:
            if 'session' in locals():
                session.close()


# 全局查询服务实例
query_service = QueryService()
