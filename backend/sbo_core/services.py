from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sbo_core.database import (
    get_database,
    RawEvent,
    ConsolidationJob,
    Conversation,
    Message,
    UserProfile,
    FileMetadata,
    EvidenceAccessStats,
)
from sbo_core.errors import (
    AppError,
    ErrorCode,
    ingest_failed,
    duplicate_event,
)
from sbo_core.models import IngestRequest, ChatRequest, UploadRequest


class EventService:
    """事件服务"""
    
    def __init__(self):
        self.db = None
    
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def create_raw_event(self, request: IngestRequest | ChatRequest | UploadRequest, user_id: str | None = None) -> uuid.UUID:
        """创建原始事件"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            # 检查幂等性
            if hasattr(request, 'idempotency_key') and request.idempotency_key:
                existing_event = session.query(RawEvent).filter(
                    RawEvent.idempotency_key == request.idempotency_key
                ).first()
                
                if existing_event:
                    raise duplicate_event(f"Duplicate event with idempotency_key: {request.idempotency_key}")
            
            # 创建事件
            event = RawEvent(
                source=request.source,
                source_message_id=getattr(request, 'source_message_id', None),
                occurred_at=request.occurred_at,
                content=request.content,
                tags=getattr(request, 'tags', []),
                idempotency_key=getattr(request, 'idempotency_key', None),
                user_id=user_id,
            )
            
            session.add(event)
            session.commit()
            session.refresh(event)
            
            return event.id
            
        except Exception as e:
            session.rollback()
            if isinstance(e, AppError):
                raise
            raise AppError(
                code=ErrorCode.INGEST_FAILED,
                message=f"Failed to create raw event: {str(e)}",
                status_code=503
            )
        finally:
            session.close()

    async def queue_consolidation_jobs(self, event_id: uuid.UUID, user_id: str | None = None) -> list[str]:
        """将巩固任务入队"""
        job_types = [
            "consolidate_event",
            "embed_event",
            "upsert_profile",
            "upsert_graph",
        ]

        db = self._get_db()
        session = db.get_session()
        job_ids = []

        try:
            for job_type in job_types:
                job = ConsolidationJob(
                    event_id=event_id,
                    job_type=job_type,
                    status="queued",
                    payload={"user_id": user_id} if user_id else {},
                )

                session.add(job)
                session.commit()
                session.refresh(job)

                job_ids.append(f"{job_type}:{job.id}")

            return job_ids

        except Exception as e:
            session.rollback()
            # 队列失败不应该阻止事件录入，只记录日志
            import logging

            logger = logging.getLogger("sbo_core")
            logger.error(f"Failed to queue consolidation jobs for event {event_id}: {e}")
            return []
        finally:
            session.close()


class EvidenceAccessService:
    def __init__(self):
        self.db = None

    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db

    async def record_access(
        self,
        *,
        user_id: str,
        evidence_ids: list[str],
        accessed_at: datetime | None = None,
    ) -> int:
        if not user_id or not evidence_ids:
            return 0

        ts = accessed_at or datetime.now(timezone.utc)

        db = self._get_db()
        session = db.get_session()
        try:
            updated = 0
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
                    row = EvidenceAccessStats(
                        user_id=user_id,
                        evidence_id=evidence_id,
                        access_count=1,
                        last_accessed_at=ts,
                    )
                    session.add(row)
                else:
                    row.access_count = int(row.access_count or 0) + 1
                    row.last_accessed_at = ts
                updated += 1

            session.commit()
            return updated
        except Exception as e:
            session.rollback()
            import logging

            logger = logging.getLogger("sbo_core")
            logger.error(f"Failed to record evidence access stats: {e}")
            return 0
        finally:
            session.close()


class ConversationService:
    """对话服务"""
    
    def __init__(self):
        self.db = None
    
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def create_conversation(self, user_id: str, title: str | None = None) -> uuid.UUID:
        """创建对话"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            from sbo_core.database import Conversation
            conversation = Conversation(
                user_id=user_id,
                title=title
            )
            
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            
            return conversation.id
            
        except Exception as e:
            session.rollback()
            raise AppError(
                code=ErrorCode.CHAT_FAILED,
                message=f"Failed to create conversation: {str(e)}",
                status_code=503
            )
        finally:
            session.close()
    
    async def add_message_to_conversation(
        self,
        conversation_id: uuid.UUID,
        event_id: uuid.UUID,
        role: str,
        content: str
    ) -> None:
        """添加消息到对话"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            from sbo_core.database import Message
            
            # 获取当前最大序列号
            max_seq = session.query(Message).filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.sequence_number.desc()).first()
            
            next_seq = (max_seq.sequence_number + 1) if max_seq else 1
            
            message = Message(
                conversation_id=conversation_id,
                event_id=event_id,
                role=role,
                content=content,
                sequence_number=next_seq
            )
            
            session.add(message)
            session.commit()
            
        except Exception as e:
            session.rollback()
            raise AppError(
                code=ErrorCode.CHAT_FAILED,
                message=f"Failed to add message to conversation: {str(e)}",
                status_code=503
            )
        finally:
            session.close()


class FileService:
    """文件服务"""
    
    def __init__(self):
        self.db = None
    
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def save_file_metadata(
        self,
        file_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str | None = None,
        user_id: str | None = None
    ) -> None:
        """保存文件元数据"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            from sbo_core.database import FileMetadata
            
            file_meta = FileMetadata(
                id=file_id,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_path=storage_path,
                user_id=user_id
            )
            
            session.add(file_meta)
            session.commit()
            
        except Exception as e:
            session.rollback()
            raise AppError(
                code=ErrorCode.UPLOAD_FAILED,
                message=f"Failed to save file metadata: {str(e)}",
                status_code=503
            )
        finally:
            session.close()


class UserProfileService:
    """用户档案服务"""
    
    def __init__(self):
        self.db = None
    
    def _get_db(self):
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户档案"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            from sbo_core.database import UserProfile
            
            profile = session.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            
            if not profile:
                return {
                    "user_id": user_id,
                    "facts": {},
                    "preferences": {},
                    "constraints": {},
                    "version": 1,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            
            return {
                "user_id": profile.user_id,
                "facts": profile.facts or {},
                "preferences": profile.preferences or {},
                "constraints": profile.constraints or {},
                "version": profile.version,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
            }
            
        except Exception as e:
            raise AppError(
                code=ErrorCode.PROFILE_NOT_FOUND,
                message=f"Failed to get user profile: {str(e)}",
                status_code=500
            )
        finally:
            session.close()
    
    async def update_profile(
        self,
        user_id: str,
        facts: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """更新用户档案"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            from sbo_core.database import UserProfile
            
            profile = session.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            
            if not profile:
                # 创建新档案
                profile = UserProfile(
                    user_id=user_id,
                    facts=facts or {},
                    preferences=preferences or {},
                    constraints=constraints or {},
                    version=1
                )
            else:
                # 更新现有档案
                if facts is not None:
                    profile.facts = {**(profile.facts or {}), **facts}
                if preferences is not None:
                    profile.preferences = {**(profile.preferences or {}), **preferences}
                if constraints is not None:
                    profile.constraints = {**(profile.constraints or {}), **constraints}
                profile.version += 1
            
            profile.updated_at = datetime.now(timezone.utc)
            
            session.add(profile)
            session.commit()
            session.refresh(profile)
            
            return {
                "user_id": profile.user_id,
                "facts": profile.facts or {},
                "preferences": profile.preferences or {},
                "constraints": profile.constraints or {},
                "version": profile.version,
                "updated_at": profile.updated_at.isoformat()
            }
            
        except Exception as e:
            session.rollback()
            raise AppError(
                code=ErrorCode.PROFILE_UPDATE_FAILED,
                message=f"Failed to update user profile: {str(e)}",
                status_code=500
            )
        finally:
            session.close()


# 全局服务实例
event_service = EventService()
evidence_access_service = EvidenceAccessService()
conversation_service = ConversationService()
file_service = FileService()
user_profile_service = UserProfileService()
