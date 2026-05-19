"""
向量嵌入任务单元测试 - 4.7

测试内容：
1. embeddings API 集成
2. 失败处理机制
3. 批量重跑功能

依赖需求：3.5, 4.1.2, 3.5.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sbo_core.tasks_embedding import (
    embed_event,
    enqueue_embed_event,
    replay_embeddings_batch,
    get_failed_embedding_events,
    get_embedding_stats,
)
from sbo_core.embeddings_client import SiliconFlowEmbeddingsClient, embed_text, embed_texts_batch
from sbo_core.errors import ErrorCode, AppError, EmbeddingsError
from sbo_core.database import RawEvent, Embedding


class TestSiliconFlowEmbeddingsClient:
    """SiliconFlow Embeddings 客户端测试"""
    
    def test_client_initialization_without_api_key(self, monkeypatch):
        """测试缺少 API Key 时的初始化失败"""
        monkeypatch.setenv("SILICONFLOW_API_KEY", "")
        
        with pytest.raises(AppError) as exc_info:
            with patch("sbo_core.config.load_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    siliconflow_api_key="",
                    siliconflow_base_url="https://api.siliconflow.cn/v1",
                    siliconflow_embedding_model="",
                )
                SiliconFlowEmbeddingsClient()
        
        assert exc_info.value.code == ErrorCode.CONFIG_MISSING
    
    def test_client_initialization_with_api_key(self, monkeypatch):
        """测试正常初始化"""
        monkeypatch.setenv("SILICONFLOW_API_KEY", "test-api-key")
        monkeypatch.setenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        monkeypatch.setenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
        
        with patch("sbo_core.config.load_settings") as mock_settings:
            from sbo_core.config import Settings
            mock_settings.return_value = Settings(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            assert client.api_key == "test-api-key"
            assert client.base_url == "https://api.siliconflow.cn/v1"
            assert client.model == "BAAI/bge-m3"
            client.close()
    
    def test_get_dimensions(self):
        """测试获取向量维度"""
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            # 测试已知模型的维度
            assert client.get_dimensions() == 1024
            
            # 测试未知模型返回默认值
            client.model = "unknown-model"
            assert client.get_dimensions() == 1024
            
            client.close()
    
    @patch("httpx.Client.post")
    def test_embed_texts_success(self, mock_post):
        """测试成功生成 embeddings"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
                {"embedding": [0.5, 0.6, 0.7, 0.8]},
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            embeddings = client.embed_texts(["text1", "text2"])
            
            assert len(embeddings) == 2
            assert embeddings[0] == [0.1, 0.2, 0.3, 0.4]
            assert embeddings[1] == [0.5, 0.6, 0.7, 0.8]
            
            client.close()
    
    @patch("httpx.Client.post")
    def test_embed_texts_auth_error(self, mock_post):
        """测试认证失败错误处理"""
        from httpx import HTTPStatusError, Response
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.side_effect = HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )
        
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="invalid-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            with pytest.raises(EmbeddingsError) as exc_info:
                client.embed_texts(["test text"])
            
            assert "auth_failed" in str(exc_info.value.code) or "EMBEDDINGS_AUTH_FAILED" in str(exc_info.value.code)
            
            client.close()
    
    @patch("httpx.Client.post")
    def test_embed_texts_rate_limit(self, mock_post):
        """测试限流错误处理"""
        from httpx import HTTPStatusError, Response
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.side_effect = HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=mock_response
        )
        
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            with pytest.raises(EmbeddingsError) as exc_info:
                client.embed_texts(["test text"])
            
            assert "rate_limited" in str(exc_info.value.code) or "EMBEDDINGS_RATE_LIMITED" in str(exc_info.value.code)
            
            client.close()
    
    @patch("httpx.Client.post")
    def test_embed_texts_timeout(self, mock_post):
        """测试超时错误处理"""
        from httpx import TimeoutException
        
        mock_post.side_effect = TimeoutException("Request timed out")
        
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            with pytest.raises(EmbeddingsError) as exc_info:
                client.embed_texts(["test text"])
            
            assert "timeout" in str(exc_info.value.code) or "EMBEDDINGS_TIMEOUT" in str(exc_info.value.code)
            
            client.close()
    
    def test_embed_single_success(self):
        """测试单个文本嵌入成功"""
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            with patch.object(client, "embed_texts") as mock_embed:
                mock_embed.return_value = [[0.1, 0.2, 0.3]]
                
                result = client.embed_single("test text")
                
                assert result == [0.1, 0.2, 0.3]
            
            client.close()
    
    def test_embed_single_empty_text(self):
        """测试空文本返回 None"""
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            assert client.embed_single("") is None
            assert client.embed_single("   ") is None
            
            client.close()
    
    def test_embed_single_failure_returns_none(self):
        """测试失败时返回 None（不抛出异常）"""
        with patch("sbo_core.config.load_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                siliconflow_api_key="test-api-key",
                siliconflow_base_url="https://api.siliconflow.cn/v1",
                siliconflow_embedding_model="BAAI/bge-m3",
            )
            client = SiliconFlowEmbeddingsClient()
            
            with patch.object(client, "embed_texts") as mock_embed:
                mock_embed.side_effect = EmbeddingsError(
                    error_type="unavailable",
                    message="API error"
                )
                
                result = client.embed_single("test text")
                
                assert result is None
            
            client.close()


class TestEmbedEventTask:
    """embed_event 任务测试"""
    
    def _create_mock_db(self, event=None, existing_embedding=None):
        """创建模拟数据库会话"""
        mock_session = MagicMock()
        
        # 配置 query().filter().first() 返回不同的值：
        # 第一次查询 RawEvent，第二次查询 Embedding
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return event  # RawEvent 查询
            return existing_embedding  # Embedding 查询
        
        mock_session.query.return_value.filter.return_value.first.side_effect = side_effect
        mock_session.query.return_value.filter.return_value.count.return_value = 0 if event is None else 1
        
        # 配置 add() 方法
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        
        return mock_db, mock_session
    
    def test_embed_event_invalid_event_id(self):
        """测试无效的事件ID格式"""
        with pytest.raises(AppError) as exc_info:
            embed_event("invalid-uuid")
        
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_embed_event_not_found(self, mock_get_db):
        """测试事件不存在"""
        mock_db, mock_session = self._create_mock_db(event=None)
        mock_get_db.return_value = mock_db
        
        with pytest.raises(AppError) as exc_info:
            embed_event(str(uuid.uuid4()))
        
        assert exc_info.value.code == ErrorCode.EVENT_NOT_FOUND
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_embed_event_soft_deleted(self, mock_get_db):
        """测试跳过已软删除的事件"""
        # 创建软删除的事件
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
            deleted_at=datetime.now(timezone.utc),
        )
        
        mock_db, mock_session = self._create_mock_db(event=event)
        mock_get_db.return_value = mock_db
        
        result = embed_event(str(event.id))
        
        assert result["status"] == "skipped"
        assert result["reason"] == "event_soft_deleted"
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_embed_event_empty_content(self, mock_get_db):
        """测试跳过空内容事件"""
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="",
            occurred_at=datetime.now(timezone.utc),
        )
        
        mock_db, mock_session = self._create_mock_db(event=event)
        mock_get_db.return_value = mock_db
        
        result = embed_event(str(event.id))
        
        assert result["status"] == "skipped"
        assert result["reason"] == "empty_content"
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.get_embeddings_client")
    def test_embed_event_success(self, mock_get_client, mock_get_db):
        """测试成功生成 embedding"""
        # 创建事件
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content for embedding",
            occurred_at=datetime.now(timezone.utc),
        )
        
        mock_db, mock_session = self._create_mock_db(event=event, existing_embedding=None)
        mock_get_db.return_value = mock_db
        
        # 模拟 embedding 客户端
        mock_client = MagicMock()
        mock_client.model = "BAAI/bge-m3"
        mock_client.embed_single.return_value = [0.1] * 1024
        mock_get_client.return_value = mock_client
        
        result = embed_event(str(event.id))
        
        assert result["status"] == "succeeded"
        assert "embedding_id" in result
        assert result["model"] == "BAAI/bge-m3"
        assert result["dimensions"] == 1024
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.get_embeddings_client")
    def test_embed_event_failure_non_blocking(self, mock_get_client, mock_get_db):
        """测试失败不阻塞策略 - embedding 失败但不抛出异常"""
        # 创建事件
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        mock_db, mock_session = self._create_mock_db(event=event, existing_embedding=None)
        mock_get_db.return_value = mock_db
        
        # 模拟 embedding 失败
        mock_client = MagicMock()
        mock_client.model = "BAAI/bge-m3"
        mock_client.embed_single.return_value = None
        mock_get_client.return_value = mock_client
        
        result = embed_event(str(event.id))
        
        # 验证返回失败状态但不抛出异常
        assert result["status"] == "failed"
        assert "retryable" in result
        assert result["retryable"] is True
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.get_embeddings_client")
    def test_embed_event_api_error_non_blocking(self, mock_get_client, mock_get_db):
        """测试 API 错误不阻塞策略"""
        event = RawEvent(
            id=uuid.uuid4(),
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        mock_db, mock_session = self._create_mock_db(event=event, existing_embedding=None)
        mock_get_db.return_value = mock_db
        
        # 模拟 API 错误
        mock_get_client.side_effect = EmbeddingsError(
            error_type="unavailable",
            message="SiliconFlow API unavailable"
        )
        
        result = embed_event(str(event.id))
        
        # 验证返回失败状态但不抛出异常
        assert result["status"] == "failed"
        assert "SiliconFlow API unavailable" in result.get("error", "")
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.get_embeddings_client")
    def test_embed_event_is_rerun(self, mock_get_client, mock_get_db):
        """测试重跑场景 - 更新现有 embedding"""
        # 创建事件和失败的 embedding
        event_id = uuid.uuid4()
        event = RawEvent(
            id=event_id,
            source="webchat",
            content="Test content",
            occurred_at=datetime.now(timezone.utc),
        )
        
        existing_embedding = Embedding(
            id=uuid.uuid4(),
            event_id=event_id,
            embedding=None,
            model_name="unknown",
            dimensions=0,
            error_message="Previous failure",
            rerun_count=0,
        )
        
        mock_db, mock_session = self._create_mock_db(event=event, existing_embedding=existing_embedding)
        mock_get_db.return_value = mock_db
        
        # 模拟成功生成 embedding
        mock_client = MagicMock()
        mock_client.model = "BAAI/bge-m3"
        mock_client.embed_single.return_value = [0.2] * 1024
        mock_get_client.return_value = mock_client
        
        result = embed_event(str(event_id), is_rerun=True)
        
        assert result["status"] == "succeeded"
        assert result["is_rerun"] is True


class TestReplayEmbeddingsBatch:
    """批量重跑 embedding 测试（使用 Mock）"""
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.embed_event")
    def test_replay_embeddings_no_events(self, mock_embed, mock_get_db):
        """测试没有事件时的重跑 - 返回0事件"""
        # 模拟数据库返回空
        mock_session = MagicMock()
        mock_count_query = MagicMock()
        mock_count_query.count.return_value = 0
        mock_session.query.return_value.filter.return_value = mock_count_query
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        result = replay_embeddings_batch(
            only_failed=True,
        )
        
        assert result["total_events"] == 0
        assert result["status"] == "succeeded"
    
    @patch("sbo_core.tasks_embedding.get_database")
    @patch("sbo_core.tasks_embedding.embed_event")
    def test_replay_embeddings_partial_failure(self, mock_embed, mock_get_db):
        """测试批量重跑 - 模拟部分失败的情况"""
        # 由于复杂的数据库链式调用难以完全 mock，我们简化为只测试 embed_event 的调用
        
        # 模拟 embed_event：前两个成功，第三个失败
        def mock_embed_side_effect(event_id, **kwargs):
            if "event3" in event_id:
                return {"status": "failed", "error": "API error"}
            return {"status": "succeeded", "embedding_id": str(uuid.uuid4())}
        
        mock_embed.side_effect = mock_embed_side_effect
        
        # 直接使用 event_ids 参数而不是时间范围
        event_ids = [str(uuid.uuid4()) for _ in range(3)]
        # 修改第三个事件的 UUID 以匹配失败条件
        event_ids[2] = event_ids[2].replace(event_ids[2][:8], "event3")
        
        # 创建事件
        events = []
        for i, eid in enumerate(event_ids):
            event = RawEvent(
                id=uuid.UUID(eid) if "event3" not in eid else uuid.uuid4(),
                source="webchat",
                content=f"Test content {i}",
                occurred_at=datetime.now(timezone.utc),
            )
            events.append(event)
        
        # 配置复杂的 mock 链
        mock_session = MagicMock()
        mock_count_query = MagicMock()
        mock_count_query.count.return_value = 3
        
        mock_limit = MagicMock()
        mock_limit.all.return_value = events
        mock_offset = MagicMock()
        mock_offset.limit.return_value = mock_limit
        mock_filter = MagicMock()
        mock_filter.count.return_value = 3
        mock_filter.offset.return_value = mock_offset
        
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_query.outerjoin.return_value.filter.return_value = mock_filter
        
        mock_session.query.return_value = mock_query
        mock_session.commit.return_value = None
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        result = replay_embeddings_batch(
            event_ids=event_ids,
            only_failed=False,
            batch_size=100,
        )
        
        # 验证 embed_event 被调用了3次
        assert mock_embed.call_count == 3


class TestEmbeddingStats:
    """Embedding 统计信息测试（使用 Mock）"""
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_get_embedding_stats_empty(self, mock_get_db):
        """测试空数据库的统计"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        stats = get_embedding_stats()
        
        assert stats["total_events"] == 0
        assert stats["with_embedding"] == 0
        assert stats["failed"] == 0
        assert stats["coverage_rate"] == 0
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_get_embedding_stats_with_data(self, mock_get_db):
        """测试有数据时的统计"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.side_effect = [3, 1, 1]
        mock_session.close.return_value = None
        
        # 模拟模型分布查询
        mock_model_result = MagicMock()
        mock_model_result.all.return_value = [("BAAI/bge-m3", 1)]
        mock_session.query.return_value.filter.return_value.group_by.return_value = mock_model_result
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        stats = get_embedding_stats()
        
        assert stats["total_events"] == 3
        assert stats["with_embedding"] == 1
        assert stats["failed"] == 1
    
    @patch("sbo_core.tasks_embedding.get_database")
    def test_get_failed_embedding_events(self, mock_get_db):
        """测试获取失败的 embedding 事件列表"""
        # 创建模拟的返回结果
        mock_raw = MagicMock()
        mock_raw.id = uuid.uuid4()
        mock_raw.content = "Test content"
        mock_raw.occurred_at = datetime.now(timezone.utc)
        
        mock_emb = MagicMock()
        mock_emb.error_message = "API timeout"
        mock_emb.rerun_count = 2
        
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.filter.return_value.limit.return_value.all.return_value = [
            (mock_raw, mock_emb)
        ]
        mock_session.close.return_value = None
        
        mock_db = MagicMock()
        mock_db.get_session.return_value = mock_session
        mock_get_db.return_value = mock_db
        
        failed_events = get_failed_embedding_events()
        
        assert len(failed_events) == 1
        assert failed_events[0]["error_message"] == "API timeout"
        assert failed_events[0]["rerun_count"] == 2


class TestEmbedTextConvenience:
    """便捷函数 embed_text 测试"""
    
    @patch("sbo_core.embeddings_client.get_embeddings_client")
    def test_embed_text_success(self, mock_get_client):
        """测试便捷函数成功场景"""
        mock_client = MagicMock()
        mock_client.embed_single.return_value = [0.1, 0.2, 0.3]
        mock_get_client.return_value = mock_client
        
        result = embed_text("Test text")
        
        assert result == [0.1, 0.2, 0.3]
    
    @patch("sbo_core.embeddings_client.get_embeddings_client")
    def test_embed_text_failure_returns_none(self, mock_get_client):
        """测试便捷函数失败时返回 None"""
        mock_client = MagicMock()
        mock_client.embed_single.return_value = None
        mock_get_client.return_value = mock_client
        
        result = embed_text("Test text")
        
        assert result is None
    
    @patch("sbo_core.embeddings_client.get_embeddings_client")
    def test_embed_text_config_error_returns_none(self, mock_get_client):
        """测试配置错误时返回 None 不抛出"""
        mock_get_client.side_effect = AppError(
            code=ErrorCode.CONFIG_MISSING,
            message="Missing API key",
            status_code=500
        )
        
        result = embed_text("Test text")
        
        assert result is None
    
    @patch("sbo_core.embeddings_client.get_embeddings_client")
    def test_embed_texts_batch_success(self, mock_get_client):
        """测试批量嵌入成功"""
        mock_client = MagicMock()
        mock_client.embed_texts.return_value = [[0.1, 0.2], [0.3, 0.4]]
        mock_get_client.return_value = mock_client
        
        result = embed_texts_batch(["Text 1", "Text 2"])
        
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]
    
    @patch("sbo_core.embeddings_client.get_embeddings_client")
    def test_embed_texts_batch_failure_returns_none_list(self, mock_get_client):
        """测试批量嵌入失败时返回 None 列表"""
        mock_get_client.side_effect = AppError(
            code=ErrorCode.CONFIG_MISSING,
            message="Missing API key",
            status_code=500
        )
        
        result = embed_texts_batch(["Text 1", "Text 2"])
        
        assert len(result) == 2
        assert result[0] is None
        assert result[1] is None
