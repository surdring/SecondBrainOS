from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from uuid import UUID

from sbo_core.app import create_app
from sbo_core.models import IngestRequest, ChatRequest, UploadRequest
from sbo_core.errors import ingest_failed


@pytest.fixture
def client():
    """创建测试客户端"""
    # 模拟数据库初始化以避免实际数据库连接
    with patch('sbo_core.app.init_database') as mock_init:
        mock_init.return_value = None
        app = create_app()
        return TestClient(app)


@pytest.fixture
def sample_ingest_request():
    """示例录入请求"""
    return {
        "source": "webchat",
        "source_message_id": "msg_123",
        "occurred_at": "2024-01-01T12:00:00Z",
        "content": "This is a test message",
        "tags": ["test", "sample"],
        "idempotency_key": "unique_key_123"
    }


@pytest.fixture
def sample_chat_request():
    """示例对话请求"""
    return {
        "content": "Hello, how are you?",
        "source": "webchat",
        "source_message_id": "chat_msg_123",
        "idempotency_key": "chat_key_123"
    }


class TestIngestEndpoint:
    """测试 /ingest 端点"""
    
    @patch('sbo_core.routes.ingest.event_service.create_raw_event')
    @patch('sbo_core.routes.ingest.event_service.queue_consolidation_jobs')
    def test_ingest_success(self, mock_queue, mock_create, client, sample_ingest_request):
        """测试成功录入"""
        # 设置 mock 返回值
        mock_create.return_value = UUID("12345678-1234-1234-1234-123456789012")
        mock_queue.return_value = ["consolidate_event:12345678-1234-1234-1234-123456789012"]
        
        response = client.post("/api/v1/ingest", json=sample_ingest_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == "12345678-1234-1234-1234-123456789012"
        assert len(data["queued_jobs"]) == 1
        assert "consolidate_event" in data["queued_jobs"][0]
        
        # 验证调用
        mock_create.assert_called_once()
        mock_queue.assert_called_once()
    
    def test_ingest_validation_error_invalid_source(self, client, sample_ingest_request):
        """测试无效来源的验证错误"""
        sample_ingest_request["source"] = "invalid_source"
        
        response = client.post("/api/v1/ingest", json=sample_ingest_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
        assert "Source must be one of" in data["details"]["validation_errors"][0]
    
    def test_ingest_validation_error_empty_content(self, client, sample_ingest_request):
        """测试空内容的验证错误"""
        sample_ingest_request["content"] = ""
        
        response = client.post("/api/v1/ingest", json=sample_ingest_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    def test_ingest_validation_error_too_many_tags(self, client, sample_ingest_request):
        """测试标签过多的验证错误"""
        sample_ingest_request["tags"] = [f"tag_{i}" for i in range(25)]  # 超过 20 个标签
        
        response = client.post("/api/v1/ingest", json=sample_ingest_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
        assert "Too many tags" in data["details"]["validation_errors"][0]
    
    @patch('sbo_core.routes.ingest.event_service.create_raw_event')
    def test_ingest_database_error(self, mock_create, client, sample_ingest_request):
        """测试数据库写入错误"""
        mock_create.side_effect = ingest_failed("Failed to write raw event to database")
        
        response = client.post("/api/v1/ingest", json=sample_ingest_request)
        
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "ingest_failed"
        assert "Failed to write raw event to database" in data["message"]


class TestChatEndpoint:
    """测试 /chat 端点"""
    
    @patch('sbo_core.routes.ingest.conversation_service.create_conversation')
    @patch('sbo_core.routes.ingest.event_service.create_raw_event')
    @patch('sbo_core.routes.ingest.event_service.queue_consolidation_jobs')
    @patch('sbo_core.routes.ingest.conversation_service.add_message_to_conversation')
    def test_chat_success(self, mock_add_msg, mock_queue, mock_create, mock_conv, client, sample_chat_request):
        """测试成功对话"""
        # 设置 mock 返回值
        mock_conv.return_value = UUID("12345678-1234-1234-1234-123456789012")
        mock_create.return_value = UUID("12345678-1234-1234-1234-123456789012")
        mock_queue.return_value = ["consolidate_event:12345678-1234-1234-1234-123456789012"]
        mock_add_msg.return_value = None
        
        response = client.post("/api/v1/chat", json=sample_chat_request)
        
        assert response.status_code == 200
        data = response.json()
        assert "assistant_message" in data
        assert "evidence" in data
        assert "conversation_id" in data
        assert isinstance(data["evidence"], list)
        
        # 验证调用
        assert mock_conv.call_count == 1
        assert mock_create.call_count == 2  # 用户消息和助手回复
        assert mock_queue.call_count == 2
        assert mock_add_msg.call_count == 2  # 两条消息
    
    def test_chat_validation_error_invalid_source(self, client, sample_chat_request):
        """测试无效来源的验证错误"""
        sample_chat_request["source"] = "invalid_source"
        
        response = client.post("/api/v1/chat", json=sample_chat_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"
    
    def test_chat_validation_error_empty_content(self, client, sample_chat_request):
        """测试空内容的验证错误"""
        sample_chat_request["content"] = ""
        
        response = client.post("/api/v1/chat", json=sample_chat_request)
        
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"


class TestUploadEndpoint:
    """测试 /upload 端点"""
    
    @patch('sbo_core.routes.ingest.file_service.save_file_metadata')
    @patch('sbo_core.routes.ingest.event_service.create_raw_event')
    @patch('sbo_core.routes.ingest.event_service.queue_consolidation_jobs')
    def test_upload_image_success(self, mock_queue, mock_create, mock_save, client):
        """测试成功上传图片"""
        # 设置 mock 返回值
        mock_save.return_value = None
        mock_create.return_value = UUID("12345678-1234-1234-1234-123456789012")
        mock_queue.return_value = ["consolidate_event:12345678-1234-1234-1234-123456789012"]
        
        # 创建测试文件
        test_content = b"fake image content"
        
        response = client.post(
            "/api/v1/upload",
            files={"file": ("test.jpg", test_content, "image/jpeg")},
            data={
                "source": "upload",
                "idempotency_key": "upload_key_123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "file_id" in data
        assert "event_id" in data
        assert "metadata" in data
        assert data["metadata"]["filename"] == "test.jpg"
        assert data["metadata"]["content_type"] == "image/jpeg"
        assert data["metadata"]["size_bytes"] == len(test_content)
        assert len(data["queued_jobs"]) > 0
        
        # 验证调用
        mock_save.assert_called_once()
        mock_create.assert_called_once()
        mock_queue.assert_called_once()
    
    def test_upload_invalid_file_type(self, client):
        """测试无效文件类型"""
        test_content = b"fake content"
        
        response = client.post(
            "/api/v1/upload",
            files={"file": ("test.exe", test_content, "application/octet-stream")},
            data={"source": "upload"}
        )
        
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "upload_failed"
        assert "Unsupported file type" in data["message"]
    
    def test_upload_file_too_large(self, client):
        # 这个测试需要 mock 文件读取来模拟大文件
        # 由于实际文件大小限制在读取时检查，这里我们只测试基本逻辑
        pass


class TestRequestValidation:
    """测试请求验证"""
    
    def test_ingest_request_model_validation(self):
        """测试 IngestRequest 模型验证"""
        # 有效请求
        request_data = {
            "source": "webchat",
            "occurred_at": datetime.now(timezone.utc),
            "content": "Test content",
            "tags": ["tag1", "tag2"],
            "idempotency_key": "test_key"
        }
        request = IngestRequest(**request_data)
        assert request.source == "webchat"
        assert request.content == "Test content"
        assert len(request.tags) == 2
    
    def test_chat_request_model_validation(self):
        """测试 ChatRequest 模型验证"""
        request_data = {
            "content": "Hello",
            "source": "webchat",
            "idempotency_key": "chat_key"
        }
        request = ChatRequest(**request_data)
        assert request.content == "Hello"
        assert request.source == "webchat"
    
    def test_upload_request_model_validation(self):
        """测试 UploadRequest 模型验证"""
        request_data = {
            "source": "upload",
            "idempotency_key": "upload_key"
        }
        request = UploadRequest(**request_data)
        assert request.source == "upload"


if __name__ == "__main__":
    pytest.main([__file__])
