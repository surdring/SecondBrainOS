from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from uuid import UUID

from sbo_core.app import create_app
from sbo_core.models import (
    QueryRequest,
    QueryResponse,
    QueryMode,
    Evidence,
    EvidenceType,
    MemoriesRequest,
    ConversationMessagesRequest,
)
from sbo_core.errors import query_failed


@pytest.fixture
def client():
    """创建测试客户端"""
    # 模拟数据库初始化以避免实际数据库连接
    with patch('sbo_core.app.init_database') as mock_init:
        mock_init.return_value = None
        app = create_app()
        return TestClient(app)


@pytest.fixture
def sample_query_request():
    """示例查询请求"""
    return {
        "query": "我昨天说了什么？",
        "top_k": 5,
        "mode": "fast",
        "user_id": "test_user"
    }


@pytest.fixture
def sample_memories_request():
    """示例记忆请求"""
    return {
        "user_id": "test_user",
        "memory_type": "event",
        "limit": 10,
        "offset": 0
    }


class TestQueryEndpoint:
    """测试 /query 端点"""
    
    @patch('sbo_core.routes.query.query_service.query')
    def test_query_success(self, mock_query, client, sample_query_request):
        """测试成功查询"""
        # 设置 mock 返回值
        mock_evidence = [
            Evidence(
                evidence_id="12345678-1234-1234-1234-123456789012",
                type=EvidenceType.RAW_EVENT,
                text="昨天你讨论了项目进展",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                confidence=0.9,
                refs={"event_id": "12345678-1234-1234-1234-123456789012"}
            )
        ]
        
        mock_query.return_value = QueryResponse(
            answer_hint="Based on your conversation yesterday...",
            evidence=mock_evidence,
            query_mode=QueryMode.FAST,
            total_candidates=1,
            processing_time_ms=150,
            degraded_services=[]
        )
        
        response = client.post("/api/v1/query", json=sample_query_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["query_mode"] == "fast"
        assert len(data["evidence"]) == 1
        assert data["total_candidates"] == 1
        assert data["processing_time_ms"] == 150
        assert len(data["degraded_services"]) == 0
        
        # 验证调用
        mock_query.assert_called_once()
    
    def test_query_validation_error_invalid_mode(self, client, sample_query_request):
        """测试无效查询模式"""
        sample_query_request["mode"] = "invalid_mode"
        
        response = client.post("/api/v1/query", json=sample_query_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    def test_query_validation_error_empty_query(self, client, sample_query_request):
        """测试空查询字符串"""
        sample_query_request["query"] = ""
        
        response = client.post("/api/v1/query", json=sample_query_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    @patch('sbo_core.routes.query.query_service.query')
    def test_query_service_error(self, mock_query, client, sample_query_request):
        """测试查询服务错误"""
        mock_query.side_effect = query_failed("Database connection failed")
        
        response = client.post("/api/v1/query", json=sample_query_request)
        
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "query_failed"
        assert "Database connection failed" in data["message"]


class TestMemoriesEndpoint:
    """测试 /memories 端点"""
    
    @patch('sbo_core.routes.query.query_service.get_memories')
    def test_get_memories_success(self, mock_get_memories, client, sample_memories_request):
        """测试成功获取记忆列表"""
        # 设置 mock 返回值
        from sbo_core.models import MemoryItem, MemoryType, MemoriesResponse
        
        mock_memories = [
            MemoryItem(
                memory_id="12345678-1234-1234-1234-123456789012",
                type=MemoryType.EVENT,
                content="讨论了项目进展",
                timestamp=datetime.now(timezone.utc),
                confidence=0.9,
                source_events=["12345678-1234-1234-1234-123456789012"]
            )
        ]
        
        mock_get_memories.return_value = MemoriesResponse(
            memories=mock_memories,
            total_count=1,
            has_more=False
        )
        
        response = client.get("/api/v1/memories", params=sample_memories_request)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
        assert data["total_count"] == 1
        assert data["has_more"] == False
        
        # 验证调用
        mock_get_memories.assert_called_once()
    
    def test_get_memories_invalid_memory_type(self, client, sample_memories_request):
        """测试无效记忆类型"""
        response = client.get("/api/v1/memories", params={**sample_memories_request, "memory_type": "invalid_type"})
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    def test_get_memories_invalid_time_format(self, client, sample_memories_request):
        """测试无效时间格式"""
        response = client.get("/api/v1/memories", params={**sample_memories_request, "start_time": "invalid_time"})
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"


class TestConversationMessagesEndpoint:
    """测试 /conversations/{id}/messages 端点"""
    
    @patch('sbo_core.routes.query.query_service.get_conversation_messages')
    def test_get_conversation_messages_success(self, mock_get_messages, client):
        """测试成功获取对话消息"""
        # 设置 mock 返回值
        from sbo_core.models import MessageItem, ConversationMessagesResponse
        
        mock_messages = [
            MessageItem(
                message_id="12345678-1234-1234-1234-123456789012",
                role="user",
                content="项目进展如何？",
                timestamp=datetime.now(timezone.utc),
                sequence_number=1,
                evidence=[]
            )
        ]
        
        conversation_id = "12345678-1234-1234-1234-123456789012"
        mock_get_messages.return_value = ConversationMessagesResponse(
            conversation_id=UUID(conversation_id),
            messages=mock_messages,
            total_count=1,
            has_more=False
        )
        
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == conversation_id
        assert len(data["messages"]) == 1
        assert data["total_count"] == 1
        assert data["has_more"] == False
        
        # 验证调用
        mock_get_messages.assert_called_once()
    
    def test_get_conversation_messages_invalid_uuid(self, client):
        """测试无效的对话ID"""
        response = client.get("/api/v1/conversations/invalid-uuid/messages")
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    @patch('sbo_core.routes.query.query_service.get_conversation_messages')
    def test_get_conversation_messages_not_found(self, mock_get_messages, client):
        """测试对话未找到"""
        from sbo_core.errors import conversation_not_found
        
        mock_get_messages.side_effect = conversation_not_found("Conversation not found")
        
        conversation_id = "12345678-1234-1234-1234-123456789012"
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "conversation_not_found"
        assert "Conversation not found" in data["message"]


class TestQueryService:
    """测试 /query 端点"""
    
    @pytest.mark.asyncio
    async def test_query_success_fast_mode(self, client, sample_query_request):
        """测试成功查询"""
        # 设置 mock 返回值
        mock_evidence = [
            Evidence(
                evidence_id="12345678-1234-1234-1234-123456789012",
                type=EvidenceType.RAW_EVENT,
                text="昨天你讨论了项目进展",
                occurred_at=datetime.now(timezone.utc),
                source="webchat",
                confidence=0.9,
                refs={"event_id": "12345678-1234-1234-1234-123456789012"}
            )
        ]
        
        mock_query = AsyncMock(return_value=QueryResponse(
            answer_hint="Based on your conversation yesterday...",
            evidence=mock_evidence,
            query_mode=QueryMode.FAST,
            total_candidates=1,
            processing_time_ms=150,
            degraded_services=[]
        ))
        
        with patch('sbo_core.routes.query.query_service.query', mock_query):
            response = client.post("/api/v1/query", json=sample_query_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["query_mode"] == "fast"
        assert len(data["evidence"]) == 1
        assert data["total_candidates"] == 1
        assert data["processing_time_ms"] == 150
        assert len(data["degraded_services"]) == 0
        
        # 验证调用
        mock_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_query_evidence_guardrails_confidence_and_topn(self, monkeypatch):
        from uuid import uuid4

        from sbo_core.models import Evidence, EvidenceType, QueryMode, QueryRequest
        from sbo_core.query_service import QueryService

        svc = QueryService()

        monkeypatch.setattr(QueryService, "_get_filtered_evidence_ids", lambda self, user_id: set())

        async def fake_process(*, query: str, top_k: int, mode: str, time_range, user_id):
            evidence: list[Evidence] = []
            for i in range(20):
                evidence.append(
                    Evidence(
                        evidence_id=str(uuid4()),
                        type=EvidenceType.RAW_EVENT,
                        text=f"e{i}",
                        occurred_at=datetime.now(timezone.utc),
                        source="test",
                        confidence=0.2 if i < 5 else 0.9,
                        refs={},
                    )
                )
            return evidence, []

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        req = QueryRequest(query="hello", top_k=50, mode=QueryMode.FAST, conversation_id=None)
        resp = await svc.query(req)

        assert len(resp.evidence) == 8
        assert all((e.confidence or 0.0) >= 0.3 for e in resp.evidence)

    @pytest.mark.asyncio
    async def test_query_cache_reuse_by_conversation_and_normalized_query(self, monkeypatch):
        from uuid import uuid4

        from sbo_core.models import Evidence, EvidenceType, QueryMode, QueryRequest
        from sbo_core.query_service import QueryService

        svc = QueryService()
        conv_id = uuid4()

        calls = {"n": 0}

        async def fake_process(*, query: str, top_k: int, mode: str, time_range, user_id):
            calls["n"] += 1
            return (
                [
                    Evidence(
                        evidence_id=str(uuid4()),
                        type=EvidenceType.RAW_EVENT,
                        text="cached",
                        occurred_at=datetime.now(timezone.utc),
                        source="test",
                        confidence=0.9,
                        refs={},
                    )
                ],
                ["p"],
            )

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        req1 = QueryRequest(query="  Hello   WORLD ", top_k=5, mode=QueryMode.FAST, conversation_id=conv_id)
        req2 = QueryRequest(query="hello world", top_k=5, mode=QueryMode.FAST, conversation_id=conv_id)

        resp1 = await svc.query(req1)
        resp2 = await svc.query(req2)

        assert calls["n"] == 1
        assert resp1.evidence[0].text == "cached"
        assert resp2.evidence[0].text == "cached"

    @pytest.mark.asyncio
    async def test_query_records_evidence_access_async_after_response(self, monkeypatch):
        from uuid import uuid4

        from sbo_core.models import Evidence, EvidenceType, QueryMode, QueryRequest
        from sbo_core.query_service import QueryService

        svc = QueryService()

        monkeypatch.setattr(QueryService, "_get_filtered_evidence_ids", lambda self, user_id: set())

        async def fake_process(*, query: str, top_k: int, mode: str, time_range, user_id):
            return (
                [
                    Evidence(
                        evidence_id="e1",
                        type=EvidenceType.RAW_EVENT,
                        text="t1",
                        occurred_at=datetime.now(timezone.utc),
                        source="test",
                        confidence=0.9,
                        refs={},
                    ),
                    Evidence(
                        evidence_id="e2",
                        type=EvidenceType.RAW_EVENT,
                        text="t2",
                        occurred_at=datetime.now(timezone.utc),
                        source="test",
                        confidence=0.9,
                        refs={},
                    ),
                ],
                [],
            )

        created: dict[str, object] = {}

        import asyncio as real_asyncio
        original_create_task = real_asyncio.create_task

        def fake_create_task(coro):
            created["coro"] = coro
            task = original_create_task(coro)
            created["task"] = task
            return task

        record_calls: dict[str, object] = {}

        async def fake_record_access(*, user_id: str, evidence_ids: list[str], accessed_at):
            record_calls["user_id"] = user_id
            record_calls["evidence_ids"] = list(evidence_ids)
            record_calls["accessed_at"] = accessed_at
            return len(evidence_ids)

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)
        monkeypatch.setattr("sbo_core.query_service.asyncio.create_task", fake_create_task)
        monkeypatch.setattr("sbo_core.query_service.evidence_access_service.record_access", fake_record_access)

        req = QueryRequest(
            query="hello",
            top_k=5,
            mode=QueryMode.FAST,
            conversation_id=uuid4(),
            user_id="u1",
        )
        resp = await svc.query(req)

        await real_asyncio.sleep(0)

        assert len(resp.evidence) == 2
        assert "coro" in created
        assert record_calls["user_id"] == "u1"
        assert record_calls["evidence_ids"] == ["e1", "e2"]


class TestQueryModels:
    """测试查询相关模型"""
    
    def test_query_request_model_validation(self):
        """测试 QueryRequest 模型验证"""
        # 有效请求
        request_data = {
            "query": "测试查询",
            "top_k": 5,
            "mode": "fast",
            "user_id": "test_user"
        }
        
        from sbo_core.models import QueryRequest
        request = QueryRequest(**request_data)
        assert request.query == "测试查询"
        assert request.top_k == 5
        assert request.mode == QueryMode.FAST
        assert request.user_id == "test_user"
    
    def test_query_request_top_k_validation(self):
        """测试 top_k 参数验证"""
        from sbo_core.models import QueryRequest
        import pytest
        
        # 测试最小值
        with pytest.raises(ValueError):
            QueryRequest(query="test", top_k=0)
        
        # 测试最大值
        with pytest.raises(ValueError):
            QueryRequest(query="test", top_k=51)
    
    def test_evidence_model_validation(self):
        """测试 Evidence 模型验证"""
        from sbo_core.models import Evidence, EvidenceType
        
        evidence = Evidence(
            evidence_id="12345678-1234-1234-1234-123456789012",
            type=EvidenceType.RAW_EVENT,
            text="测试证据",
            occurred_at=datetime.now(timezone.utc),
            source="test",
            confidence=0.9,
            refs={"test": "ref"}
        )
        
        assert evidence.type == EvidenceType.RAW_EVENT
        assert evidence.confidence == 0.9
        assert evidence.text == "测试证据"
    
    def test_query_response_model_validation(self):
        """测试 QueryResponse 模型验证"""
        from sbo_core.models import QueryResponse, QueryMode, Evidence, EvidenceType
        
        evidence = [
            Evidence(
                evidence_id="12345678-1234-1234-1234-123456789012",
                type=EvidenceType.RAW_EVENT,
                text="测试证据",
                occurred_at=datetime.now(timezone.utc),
                source="test",
                confidence=0.9,
                refs={}
            )
        ]
        
        response = QueryResponse(
            answer_hint="测试答案",
            evidence=evidence,
            query_mode=QueryMode.FAST,
            total_candidates=1,
            processing_time_ms=100,
            degraded_services=[]
        )
        
        assert response.answer_hint == "测试答案"
        assert len(response.evidence) == 1
        assert response.query_mode == QueryMode.FAST
        assert response.processing_time_ms == 100
        assert len(response.degraded_services) == 0
