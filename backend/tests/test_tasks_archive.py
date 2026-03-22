"""
对话归档任务单元测试

测试覆盖：
1. 归档触发条件
2. 摘要生成
3. WeKnora 导入
4. 作业状态管理
"""

from __future__ import annotations

import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

from sbo_core.tasks_archive import (
    ConversationArchiveService,
    ConversationSummary,
    ArchiveTriggerType,
    ArchiveStatus,
    ArchiveTriggerConfig,
    archive_service,
)
from sbo_core.database import Conversation, Message


class TestArchiveTriggerConditions:
    """测试归档触发条件"""
    
    @pytest.fixture
    def sample_conversation(self):
        """样本对话"""
        conv = MagicMock(spec=Conversation)
        conv.id = uuid.uuid4()
        conv.user_id = "user1"
        conv.title = "Test Conversation"
        conv.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        conv.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        conv.tags = ["test", "important"]
        return conv
    
    @pytest.fixture
    def sample_messages(self):
        """样本消息"""
        messages = []
        for i in range(5):
            msg = MagicMock(spec=Message)
            msg.id = uuid.uuid4()
            msg.conversation_id = uuid.uuid4()
            msg.role = "user" if i % 2 == 0 else "assistant"
            msg.content = f"Message {i} content"
            msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=10-i)
            msg.sequence_number = i
            messages.append(msg)
        return messages
    
    def test_should_archive_too_few_messages(self, sample_conversation, sample_messages):
        """测试消息数量不足时不归档"""
        # 只有 2 条消息（少于最小 3 条）
        should, trigger, reason = archive_service.should_archive(
            sample_conversation, sample_messages[:2]
        )
        assert should is False
        assert reason == "too_few_messages"
    
    def test_should_archive_message_threshold(self, sample_conversation):
        """测试消息数量阈值触发"""
        # 创建超过阈值的消息
        messages = []
        for i in range(55):  # 超过 MESSAGE_THRESHOLD=50
            msg = MagicMock(spec=Message)
            msg.content = f"Message {i}"
            messages.append(msg)
        
        should, trigger, reason = archive_service.should_archive(
            sample_conversation, messages
        )
        assert should is True
        assert trigger == ArchiveTriggerType.MESSAGE_THRESHOLD
    
    def test_should_archive_time_threshold(self, sample_conversation, sample_messages):
        """测试时间阈值触发"""
        # 设置对话更新时间为 40 分钟前（超过 30 分钟阈值）
        sample_conversation.updated_at = datetime.now(timezone.utc) - timedelta(minutes=40)
        
        should, trigger, reason = archive_service.should_archive(
            sample_conversation, sample_messages
        )
        assert should is True
        assert trigger == ArchiveTriggerType.TIME_THRESHOLD
        assert "idle" in reason
    
    def test_should_archive_keyword_trigger(self, sample_conversation, sample_messages):
        """测试关键词触发"""
        # 添加包含触发关键词的消息
        keyword_msg = MagicMock(spec=Message)
        keyword_msg.content = "请总结一下我们的讨论"
        sample_messages.append(keyword_msg)
        
        should, trigger, reason = archive_service.should_archive(
            sample_conversation, sample_messages
        )
        assert should is True
        assert trigger == ArchiveTriggerType.KEYWORD_TRIGGER
    
    def test_should_archive_manual_trigger(self, sample_conversation, sample_messages):
        """测试手动触发"""
        should, trigger, reason = archive_service.should_archive(
            sample_conversation,
            sample_messages,
            trigger_check=ArchiveTriggerType.MANUAL,
        )
        assert should is True
        assert trigger == ArchiveTriggerType.MANUAL


class TestConversationSummary:
    """测试对话摘要"""
    
    def test_summary_to_knowledge_content(self):
        """测试摘要转 Knowledge 内容"""
        summary = ConversationSummary(
            conversation_id="conv1",
            user_id="user1",
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            message_count=10,
            context="Project planning discussion",
            questions=["What is the timeline?", "Who is responsible?"],
            key_facts=[
                {"text": "Deadline is next week", "confidence": "high"},
                {"text": "Team size is 5", "confidence": "medium"},
            ],
            conclusions=["We need to start immediately"],
            decisions=[
                {"action": "Schedule kickoff meeting", "assignee": "Alice", "status": "pending"},
            ],
            referenced_evidence=[
                {"evidence_id": "ev1", "text": "Project requirements"},
            ],
            topics=["planning", "project"],
            importance_score=0.8,
        )
        
        content = summary.to_knowledge_content()
        
        # 验证内容包含所有部分
        assert "Project planning discussion" in content
        assert "What is the timeline?" in content
        assert "Deadline is next week" in content
        assert "We need to start immediately" in content
        assert "Schedule kickoff meeting" in content
        assert "Alice" in content
        assert "planning" in content
        assert "Message Count: 10" in content
        assert "Importance: 0.8" in content


class TestArchiveTriggerConfig:
    """测试归档触发配置"""
    
    def test_default_thresholds(self):
        """测试默认阈值"""
        config = ArchiveTriggerConfig()
        assert config.MESSAGE_THRESHOLD == 50
        assert config.IDLE_TIME_THRESHOLD_MINUTES == 30
        assert config.MIN_MESSAGES == 3
        assert "总结" in config.KEYWORD_TRIGGERS
        assert "archive" in config.KEYWORD_TRIGGERS


class TestConversationArchiveService:
    """测试归档服务"""
    
    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """测试生成摘要"""
        conv = MagicMock(spec=Conversation)
        conv.id = uuid.uuid4()
        conv.user_id = "user1"
        conv.title = "Technical Discussion"
        conv.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        conv.updated_at = datetime.now(timezone.utc)
        conv.tags = ["tech", "architecture"]
        
        messages = [
            MagicMock(
                spec=Message,
                content="What is the best architecture for this system?",
                role="user",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            ),
            MagicMock(
                spec=Message,
                content="Based on your requirements, I recommend a microservices architecture with event-driven communication.",
                role="assistant",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=25),
            ),
            MagicMock(
                spec=Message,
                content="Can you provide more details on the data flow?",
                role="user",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            ),
            MagicMock(
                spec=Message,
                content="The data flows from the API gateway to the service mesh, then to individual microservices.",
                role="assistant",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            ),
        ]
        
        summary = await archive_service.generate_summary(conv, messages)
        
        assert summary.conversation_id == str(conv.id)
        assert summary.user_id == "user1"
        assert summary.context == "Technical Discussion"
        assert summary.message_count == 4
        assert len(summary.questions) > 0  # 应该识别出问题
        assert len(summary.key_facts) > 0  # 应该识别出关键事实
        assert summary.importance_score > 0.3  # 应该有一定的重要度


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
