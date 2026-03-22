from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class RawEvent(Base):
    """原始事件表 - 事实源"""
    __tablename__ = "raw_events"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False, index=True)
    source_message_id = Column(String(255), nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True, default=list)
    idempotency_key = Column(String(255), nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 用户隔离字段
    user_id = Column(String(100), nullable=True, index=True)
    
    # 软删除字段
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class ConsolidationJob(Base):
    """巩固任务表"""
    __tablename__ = "consolidation_jobs"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(PostgresUUID(as_uuid=True), nullable=False, index=True)
    job_type = Column(String(50), nullable=False)  # consolidate_event, embed_event, upsert_profile, upsert_graph
    status = Column(String(20), nullable=False, default="queued")  # queued, running, succeeded, failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class EvidenceFeedback(Base):
    __tablename__ = "evidence_feedback"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=True, index=True)
    evidence_id = Column(String(255), nullable=False, index=True)
    feedback_type = Column(String(50), nullable=False, index=True)
    user_correction = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True, index=True)
    query = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # 任务载荷
    payload = Column(JSON, nullable=True)


class EvidenceAccessStats(Base):
    __tablename__ = "evidence_access_stats"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True)
    evidence_id = Column(String(255), nullable=False, index=True)
    access_count = Column(Integer, nullable=False, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Conversation(Base):
    """对话表"""
    __tablename__ = "conversations"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 软删除字段
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class Message(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(PostgresUUID(as_uuid=True), nullable=False, index=True)
    event_id = Column(PostgresUUID(as_uuid=True), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # 排序字段
    sequence_number = Column(Integer, nullable=False)


class UserProfile(Base):
    """用户档案表"""
    __tablename__ = "user_profiles"
    
    user_id = Column(String(100), primary_key=True)
    facts = Column(JSON, nullable=True, default=dict)
    preferences = Column(JSON, nullable=True, default=dict)
    constraints = Column(JSON, nullable=True, default=dict)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EraseJob(Base):
    """擦除作业表"""
    __tablename__ = "erase_jobs"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued")  # queued, running, succeeded, failed
    time_range_start = Column(DateTime(timezone=True), nullable=True)
    time_range_end = Column(DateTime(timezone=True), nullable=True)
    tags = Column(JSON, nullable=True, default=list)
    event_ids = Column(JSON, nullable=True, default=list)
    affected_events = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FileMetadata(Base):
    """文件元数据表"""
    __tablename__ = "file_metadata"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # 用户隔离
    user_id = Column(String(100), nullable=True, index=True)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, database_url: str):
        if database_url.startswith("sqlite:///:memory:"):
            self.engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """创建所有表"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()


# 全局数据库管理器实例
_db_manager: DatabaseManager | None = None


def init_database(database_url: str) -> DatabaseManager:
    """初始化数据库"""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    _db_manager.create_tables()
    return _db_manager


def get_database() -> DatabaseManager:
    """获取数据库管理器"""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_manager
