"""
对话归档（摘要）写入 WeKnora 任务实现 - 4.1.1

功能：
1. 定义归档触发条件（会话结束/阈值/关键事件等）
2. 生成结构化摘要（背景/问题/关键事实/结论/决策/证据）并作为 Knowledge 写入 WeKnora
3. 记录导入作业状态（成功/失败/重试）并可观测
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sbo_core.tasks_framework import (
    task_wrapper, enqueue_task, QUEUE_ARCHIVE, TaskPriority, TaskStatus
)
from sbo_core.audit import audit_log
from sbo_core.database import get_database, Conversation, Message, IngestionJob
from sbo_core.config import load_settings
from sbo_core.weknora_client import WeKnoraClient, KnowledgeCreatePayload
from sbo_core.errors import ErrorCode, AppError


_logger = logging.getLogger("sbo_core.archive_tasks")


class ArchiveTriggerType(str, Enum):
    """归档触发类型"""
    SESSION_END = "session_end"           # 会话结束
    MESSAGE_THRESHOLD = "message_threshold"  # 消息数量阈值
    TIME_THRESHOLD = "time_threshold"       # 时间阈值（会话空闲超时）
    KEYWORD_TRIGGER = "keyword_trigger"     # 关键词触发
    MANUAL = "manual"                       # 手动触发


class ArchiveStatus(str, Enum):
    """归档状态"""
    PENDING = "pending"           # 等待处理
    SUMMARIZING = "summarizing"   # 生成摘要中
    IMPORTING = "importing"       # 导入 WeKnora 中
    COMPLETED = "completed"       # 完成
    FAILED = "failed"             # 失败


class IngestionJobStatus(str, Enum):
    """导入作业状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class ConversationSummary:
    """对话结构化摘要"""
    # 基础信息
    conversation_id: str
    user_id: str
    start_time: datetime
    end_time: datetime
    message_count: int
    
    # 结构化内容
    context: str = ""                    # 背景/上下文
    questions: list[str] = field(default_factory=list)      # 问题列表
    key_facts: list[dict[str, Any]] = field(default_factory=list)  # 关键事实
    conclusions: list[str] = field(default_factory=list)    # 结论
    decisions: list[dict[str, Any]] = field(default_factory=list)   # 决策/行动项
    referenced_evidence: list[dict[str, Any]] = field(default_factory=list)  # 引用的证据
    
    # 元数据
    topics: list[str] = field(default_factory=list)           # 主题标签
    importance_score: float = 0.5                             # 重要度评分 (0-1)
    
    def to_knowledge_content(self) -> str:
        """转换为 Knowledge 内容格式"""
        lines = [
            f"# Conversation Summary: {self.conversation_id}",
            "",
            "## Context",
            self.context if self.context else "General conversation",
            "",
        ]
        
        if self.questions:
            lines.extend(["## Questions Asked", ""])
            for q in self.questions:
                lines.append(f"- {q}")
            lines.append("")
        
        if self.key_facts:
            lines.extend(["## Key Facts", ""])
            for fact in self.key_facts:
                fact_text = fact.get("text", "")
                fact_confidence = fact.get("confidence", "unknown")
                lines.append(f"- {fact_text} (confidence: {fact_confidence})")
            lines.append("")
        
        if self.conclusions:
            lines.extend(["## Conclusions", ""])
            for c in self.conclusions:
                lines.append(f"- {c}")
            lines.append("")
        
        if self.decisions:
            lines.extend(["## Decisions & Action Items", ""])
            for d in self.decisions:
                action = d.get("action", "")
                assignee = d.get("assignee", "")
                due = d.get("due_date", "")
                status = d.get("status", "pending")
                lines.append(f"- [ ] {action}")
                if assignee:
                    lines.append(f"  - Assignee: {assignee}")
                if due:
                    lines.append(f"  - Due: {due}")
                lines.append(f"  - Status: {status}")
            lines.append("")
        
        if self.referenced_evidence:
            lines.extend(["## Referenced Evidence", ""])
            for ev in self.referenced_evidence:
                ev_id = ev.get("evidence_id", "")
                ev_text = ev.get("text", "")[:100]  # 截断
                lines.append(f"- {ev_id}: {ev_text}...")
            lines.append("")
        
        # 元数据
        lines.extend([
            "## Metadata",
            f"- Start Time: {self.start_time.isoformat()}",
            f"- End Time: {self.end_time.isoformat()}",
            f"- Message Count: {self.message_count}",
            f"- Topics: {', '.join(self.topics) if self.topics else 'N/A'}",
            f"- Importance: {self.importance_score:.2f}",
        ])
        
        return "\n".join(lines)


@dataclass
class ArchiveJobResult:
    """归档作业结果"""
    job_id: str
    status: ArchiveStatus
    conversation_id: str
    knowledge_id: str | None
    trigger_type: ArchiveTriggerType
    summary: ConversationSummary | None
    error_message: str | None


class ArchiveTriggerConfig:
    """归档触发配置"""
    
    # 消息数量阈值（超过该数量触发归档）
    MESSAGE_THRESHOLD = 50
    
    # 时间阈值（会话空闲超过该时间触发归档，单位：分钟）
    IDLE_TIME_THRESHOLD_MINUTES = 30
    
    # 关键词触发列表
    KEYWORD_TRIGGERS = [
        "总结一下", "总结", "摘要", "归档", "archive", "summary",
        "重要", "关键", "决策", "决定", "action item", "todo",
    ]
    
    # 最小消息数（低于该数量不触发归档）
    MIN_MESSAGES = 3


class ConversationArchiveService:
    """对话归档服务"""
    
    def __init__(self):
        self._config = ArchiveTriggerConfig()
    
    def should_archive(
        self,
        conversation: Conversation,
        messages: list[Message],
        trigger_check: ArchiveTriggerType | None = None,
    ) -> tuple[bool, ArchiveTriggerType, str]:
        """
        判断是否应该归档对话
        
        Args:
            conversation: 对话对象
            messages: 消息列表
            trigger_check: 指定检查某个触发类型（可选）
            
        Returns:
            (should_archive, trigger_type, reason)
        """
        if len(messages) < self._config.MIN_MESSAGES:
            return False, ArchiveTriggerType.MANUAL, "too_few_messages"
        
        now = datetime.now(timezone.utc)
        
        # 检查指定的触发类型
        if trigger_check:
            if trigger_check == ArchiveTriggerType.SESSION_END:
                return True, ArchiveTriggerType.SESSION_END, "explicit_session_end"
            elif trigger_check == ArchiveTriggerType.MANUAL:
                return True, ArchiveTriggerType.MANUAL, "explicit_manual_trigger"
        
        # 消息数量阈值检查
        if len(messages) >= self._config.MESSAGE_THRESHOLD:
            return True, ArchiveTriggerType.MESSAGE_THRESHOLD, f"message_count_{len(messages)}"
        
        # 时间阈值检查（基于最后更新时间）
        last_updated = conversation.updated_at or conversation.created_at
        if last_updated:
            idle_minutes = (now - last_updated).total_seconds() / 60
            if idle_minutes >= self._config.IDLE_TIME_THRESHOLD_MINUTES:
                return True, ArchiveTriggerType.TIME_THRESHOLD, f"idle_{idle_minutes:.0f}m"
        
        # 关键词触发检查
        all_content = " ".join([m.content for m in messages]).lower()
        for keyword in self._config.KEYWORD_TRIGGERS:
            if keyword.lower() in all_content:
                return True, ArchiveTriggerType.KEYWORD_TRIGGER, f"keyword_{keyword}"
        
        return False, ArchiveTriggerType.MANUAL, "no_trigger_matched"
    
    async def generate_summary(
        self,
        conversation: Conversation,
        messages: list[Message],
    ) -> ConversationSummary:
        """
        生成对话结构化摘要
        
        Args:
            conversation: 对话对象
            messages: 消息列表
            
        Returns:
            ConversationSummary 对象
        """
        # 基础信息
        message_count = len(messages)
        start_time = min(m.created_at for m in messages if m.created_at) if messages else conversation.created_at
        end_time = max(m.created_at for m in messages if m.created_at) if messages else conversation.updated_at
        
        # 用户ID
        user_id = conversation.user_id
        
        # 提取问题和关键事实（简化实现）
        questions = []
        key_facts = []
        conclusions = []
        decisions = []
        referenced_evidence = []
        topics = []
        
        for msg in messages:
            content = msg.content
            
            # 识别问题
            if "?" in content or "？" in content or any(
                kw in content.lower() for kw in ["what", "how", "why", "where", "when", "who", "which", "是否", "什么", "怎么", "为什么"]
            ):
                if len(content) < 200:  # 简短问题
                    questions.append(content[:150])
            
            # 识别结论（简化）
            if any(kw in content.lower() for kw in ["conclusion", "结论", "决定", "确定", "综上"]):
                conclusions.append(content[:200])
            
            # 识别决策/行动项
            if any(kw in content.lower() for kw in ["action item", "todo", "任务", "待办", "决定", "decision"]):
                decisions.append({
                    "action": content[:200],
                    "status": "pending",
                })
            
            # 提取关键事实（助手回复中的关键信息）
            if msg.role == "assistant" and len(content) > 50:
                # 简单启发式：长回复可能包含关键事实
                sentences = [s.strip() for s in content.split("。") if len(s.strip()) > 20]
                for sent in sentences[:3]:  # 最多 3 句
                    key_facts.append({
                        "text": sent[:200],
                        "confidence": "medium",
                    })
        
        # 去重
        questions = list(dict.fromkeys(questions))[:10]  # 最多 10 个问题
        conclusions = list(dict.fromkeys(conclusions))[:5]
        
        # 计算重要度（启发式）
        importance_score = min(
            0.3 +  # 基础分
            len(messages) * 0.01 +  # 消息数加分
            len(questions) * 0.05 +  # 问题数加分
            len(key_facts) * 0.03 +  # 事实数加分
            len(decisions) * 0.1,   # 决策数加分
            1.0
        )
        
        # 提取主题（从标签或关键词）
        if hasattr(conversation, 'tags') and conversation.tags:
            topics = conversation.tags[:5]
        
        return ConversationSummary(
            conversation_id=str(conversation.id),
            user_id=user_id,
            start_time=start_time or datetime.now(timezone.utc),
            end_time=end_time or datetime.now(timezone.utc),
            message_count=message_count,
            context=conversation.title or "General conversation",
            questions=questions,
            key_facts=key_facts,
            conclusions=conclusions,
            decisions=decisions,
            referenced_evidence=referenced_evidence,
            topics=topics,
            importance_score=importance_score,
        )
    
    async def archive_conversation(
        self,
        conversation_id: str,
        trigger_type: ArchiveTriggerType = ArchiveTriggerType.MANUAL,
    ) -> ArchiveJobResult:
        """
        归档对话到 WeKnora
        
        Args:
            conversation_id: 对话 ID
            trigger_type: 触发类型
            
        Returns:
            ArchiveJobResult
        """
        job_id = str(uuid.uuid4())
        
        try:
            db = get_database()
            session = db.get_session()
            
            try:
                # 获取对话和消息
                conversation = session.query(Conversation).filter(
                    Conversation.id == uuid.UUID(conversation_id)
                ).first()
                
                if not conversation:
                    raise ValueError(f"Conversation not found: {conversation_id}")
                
                messages = session.query(Message).filter(
                    Message.conversation_id == uuid.UUID(conversation_id)
                ).order_by(Message.sequence_number).all()
                
                # 检查是否应该归档
                should_archive, actual_trigger, reason = self.should_archive(
                    conversation, messages, trigger_type
                )
                
                if not should_archive:
                    return ArchiveJobResult(
                        job_id=job_id,
                        status=ArchiveStatus.FAILED,
                        conversation_id=conversation_id,
                        knowledge_id=None,
                        trigger_type=actual_trigger,
                        summary=None,
                        error_message=f"Archive condition not met: {reason}",
                    )
                
                # 生成摘要
                summary = await self.generate_summary(conversation, messages)
                
                # 创建导入作业记录
                ingestion_job = IngestionJob(
                    id=uuid.UUID(job_id),
                    kb_id=None,  # 由 WeKnora 响应填充
                    source_type="conversation_summary",
                    status=IngestionJobStatus.RUNNING,
                    total_items=1,
                )
                session.add(ingestion_job)
                session.commit()
                
            finally:
                session.close()
            
            # 写入 WeKnora
            settings = load_settings()
            if not settings.weknora_enable:
                raise RuntimeError("WeKnora is not enabled")
            
            client = WeKnoraClient(
                base_url=settings.weknora_base_url,
                api_key=settings.weknora_api_key,
                timeout_ms=settings.weknora_request_timeout_ms,
            )
            
            knowledge_payload = KnowledgeCreatePayload(
                title=f"Conversation: {summary.context[:50]}..." if len(summary.context) > 50 else f"Conversation: {summary.context}",
                content=summary.to_knowledge_content(),
                tags=["conversation_summary", "auto_archived"] + summary.topics,
                metadata={
                    "conversation_id": conversation_id,
                    "user_id": summary.user_id,
                    "message_count": summary.message_count,
                    "importance_score": summary.importance_score,
                    "archive_trigger": actual_trigger.value,
                    "archive_reason": reason,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            
            knowledge = await client.create_knowledge(
                kb_id=settings.weknora_knowledge_base_id or None,
                payload=knowledge_payload,
            )
            
            # 更新作业状态
            db = get_database()
            session = db.get_session()
            try:
                ingestion_job = session.query(IngestionJob).filter(
                    IngestionJob.id == uuid.UUID(job_id)
                ).first()
                
                if ingestion_job:
                    ingestion_job.status = IngestionJobStatus.SUCCEEDED
                    ingestion_job.completed_at = datetime.now(timezone.utc)
                    ingestion_job.processed_items = 1
                    ingestion_job.kb_id = knowledge.id if knowledge else None
                
                session.commit()
            finally:
                session.close()
            
            audit_log(
                event="conversation.archive",
                outcome="success",
                details={
                    "job_id": job_id,
                    "conversation_id": conversation_id,
                    "knowledge_id": knowledge.id if knowledge else None,
                    "trigger_type": actual_trigger.value,
                    "message_count": summary.message_count,
                    "importance_score": summary.importance_score,
                }
            )
            
            return ArchiveJobResult(
                job_id=job_id,
                status=ArchiveStatus.COMPLETED,
                conversation_id=conversation_id,
                knowledge_id=knowledge.id if knowledge else None,
                trigger_type=actual_trigger,
                summary=summary,
                error_message=None,
            )
            
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Failed to archive conversation {conversation_id}: {error_msg}")
            
            # 更新作业状态为失败
            try:
                db = get_database()
                session = db.get_session()
                try:
                    ingestion_job = session.query(IngestionJob).filter(
                        IngestionJob.id == uuid.UUID(job_id)
                    ).first()
                    
                    if ingestion_job:
                        ingestion_job.status = IngestionJobStatus.FAILED
                        ingestion_job.completed_at = datetime.now(timezone.utc)
                        ingestion_job.error_message = error_msg
                    else:
                        # 创建失败记录
                        ingestion_job = IngestionJob(
                            id=uuid.UUID(job_id),
                            kb_id=None,
                            source_type="conversation_summary",
                            status=IngestionJobStatus.FAILED,
                            error_message=error_msg,
                            total_items=1,
                            processed_items=0,
                        )
                        session.add(ingestion_job)
                    
                    session.commit()
                finally:
                    session.close()
            except Exception as log_e:
                _logger.error(f"Failed to log archive failure: {log_e}")
            
            audit_log(
                event="conversation.archive",
                outcome="fail",
                details={
                    "job_id": job_id,
                    "conversation_id": conversation_id,
                    "trigger_type": trigger_type.value,
                    "error": error_msg,
                }
            )
            
            return ArchiveJobResult(
                job_id=job_id,
                status=ArchiveStatus.FAILED,
                conversation_id=conversation_id,
                knowledge_id=None,
                trigger_type=trigger_type,
                summary=None,
                error_message=error_msg,
            )


# 全局服务实例
archive_service = ConversationArchiveService()


@task_wrapper(max_retries=3, timeout=600)  # 10 分钟超时
def archive_conversation_task(
    conversation_id: str,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    """
    异步归档对话任务
    
    Args:
        conversation_id: 对话 ID
        trigger_type: 触发类型（session_end/message_threshold/time_threshold/keyword_trigger/manual）
        
    Returns:
        归档结果
    """
    import asyncio
    
    trigger = ArchiveTriggerType(trigger_type)
    result = asyncio.run(archive_service.archive_conversation(conversation_id, trigger))
    
    return {
        "job_id": result.job_id,
        "status": result.status.value,
        "conversation_id": result.conversation_id,
        "knowledge_id": result.knowledge_id,
        "trigger_type": result.trigger_type.value,
        "error_message": result.error_message,
    }


def enqueue_conversation_archive(
    conversation_id: str,
    trigger_type: ArchiveTriggerType = ArchiveTriggerType.MANUAL,
    job_id: str | None = None,
) -> Any:
    """
    将对话归档任务入队
    
    Args:
        conversation_id: 对话 ID
        trigger_type: 触发类型
        job_id: 自定义 job ID
        
    Returns:
        RQ Job 实例
    """
    return enqueue_task(
        archive_conversation_task,
        conversation_id,
        trigger_type.value,
        queue_name=QUEUE_ARCHIVE,
        priority=TaskPriority.HIGH,
        job_id=job_id,
        timeout=600,  # 10 分钟
        max_retries=3,
        retry_intervals=[30, 120, 300],  # 30秒、2分钟、5分钟
    )


def check_and_enqueue_auto_archive(conversation_id: str) -> Any | None:
    """
    检查并自动触发归档
    
    在适当的时候调用此函数（如会话结束时），自动检查是否满足归档条件
    
    Args:
        conversation_id: 对话 ID
        
    Returns:
        RQ Job 实例或 None（如果不满足条件）
    """
    import asyncio
    
    async def check():
        db = get_database()
        session = db.get_session()
        
        try:
            conversation = session.query(Conversation).filter(
                Conversation.id == uuid.UUID(conversation_id)
            ).first()
            
            if not conversation:
                return None
            
            messages = session.query(Message).filter(
                Message.conversation_id == uuid.UUID(conversation_id)
            ).all()
            
            should_archive, trigger_type, _ = archive_service.should_archive(
                conversation, messages
            )
            
            return (should_archive, trigger_type) if should_archive else None
        finally:
            session.close()
    
    result = asyncio.run(check())
    
    if result:
        should_archive, trigger_type = result
        return enqueue_conversation_archive(conversation_id, trigger_type)
    
    return None
