from __future__ import annotations

import os
import pathlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sbo_core.app import create_app
from sbo_core.database import init_database
from sbo_core.models import KnowledgeBaseRequest, IngestionRequest


def _load_env_file_if_present() -> None:
    if os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL"):
        return
    env_path = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        os.environ.setdefault(k, v)


@pytest.fixture
def sqlite_db_url(tmp_path):
    """SQLite file database for testing"""
    db_file = tmp_path / "test.db"
    return f"sqlite:///{db_file}"


@pytest.fixture
def client(sqlite_db_url):
    """创建测试客户端（真实数据库）"""
    init_database(sqlite_db_url)
    app = create_app()
    return TestClient(app)


class TestEpisodicKnowledgeBases:
    """测试 Episodic KnowledgeBase 端点"""

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_list_knowledge_bases_success(self, mock_get_client, client):
        """测试成功获取 knowledge base 列表"""
        mock_client = AsyncMock()
        mock_client.list_knowledge_bases.return_value = [
            {"id": "kb-001", "name": "Test KB 1"},
            {"id": "kb-002", "name": "Test KB 2"},
        ]
        mock_get_client.return_value = mock_client

        response = client.get("/api/v1/episodic/knowledge-bases")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["data"][0]["id"] == "kb-001"

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_list_knowledge_bases_weknora_error(self, mock_get_client, client):
        """测试 WeKnora 错误处理"""
        from sbo_core.errors import WeKnoraError

        mock_client = AsyncMock()
        mock_client.list_knowledge_bases.side_effect = WeKnoraError(
            error_type="unavailable",
            message="WeKnora service unavailable",
        )
        mock_get_client.return_value = mock_client

        response = client.get("/api/v1/episodic/knowledge-bases")

        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "knowledge_base_failed"

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_create_knowledge_base_success(self, mock_get_client, client):
        """测试成功创建 knowledge base"""
        mock_client = AsyncMock()
        mock_client.create_knowledge_base.return_value = {
            "id": "kb-new-001",
            "name": "New KB",
            "description": "Test description",
            "created_at": "2026-03-21T10:00:00Z",
            "updated_at": "2026-03-21T10:00:00Z",
        }
        mock_get_client.return_value = mock_client

        request_data = {
            "name": "New KB",
            "description": "Test description",
            "tags": ["test"],
            "metadata": {},
        }

        response = client.post("/api/v1/episodic/knowledge-bases", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["kb_id"] == "kb-new-001"
        assert data["name"] == "New KB"

    def test_create_knowledge_base_validation_error(self, client):
        """测试缺少必填字段返回 422"""
        request_data = {
            "description": "Missing name field"
        }

        response = client.post("/api/v1/episodic/knowledge-bases", json=request_data)

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"


class TestEpisodicIngestions:
    """测试 Episodic Ingestion 端点"""

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_create_ingestion_success(self, mock_get_client, client):
        """测试成功创建 ingestion job"""
        mock_client = AsyncMock()
        mock_client.create_ingestion.return_value = {
            "id": "ingest-001",
            "kb_id": "kb-001",
            "source_type": "file",
            "status": "queued",
        }
        mock_get_client.return_value = mock_client

        request_data = {
            "kb_id": str(uuid.uuid4()),
            "source_type": "file",
            "source_payload": {"file_path": "/path/to/file.pdf"},
            "tags": ["doc"],
        }

        response = client.post("/api/v1/episodic/ingestions", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "ingestion_job_id" in data

    def test_create_ingestion_invalid_source_type(self, client):
        """测试无效的 source_type 返回 422"""
        request_data = {
            "kb_id": str(uuid.uuid4()),
            "source_type": "invalid_type",
            "source_payload": {},
        }

        response = client.post("/api/v1/episodic/ingestions", json=request_data)

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_get_ingestion_status_success(self, mock_get_client, client):
        """测试成功获取 ingestion job 状态"""
        mock_client = AsyncMock()
        mock_client.get_ingestion.return_value = {
            "id": "ingest-001",
            "kb_id": "kb-001",
            "status": "succeeded",
            "source_type": "file",
            "created_at": "2026-03-21T10:00:00Z",
            "started_at": "2026-03-21T10:01:00Z",
            "completed_at": "2026-03-21T10:05:00Z",
            "processed_items": 100,
            "total_items": 100,
        }
        mock_get_client.return_value = mock_client

        response = client.get("/api/v1/episodic/ingestions/ingest-001")

        assert response.status_code == 200
        data = response.json()
        assert data["ingestion_job_id"] == "ingest-001"
        assert data["status"] == "succeeded"

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_get_ingestion_status_not_found(self, mock_get_client, client):
        """测试 ingestion job 不存在返回 404"""
        from sbo_core.errors import WeKnoraError

        mock_client = AsyncMock()
        # 使用 not_found 作为 error_type，会被映射为 ErrorCode.WEKNORA_NOT_FOUND
        mock_client.get_ingestion.side_effect = WeKnoraError(
            error_type="not_found",
            message="Ingestion job not found",
        )
        mock_get_client.return_value = mock_client

        response = client.get("/api/v1/episodic/ingestions/non-existent-id")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "ingestion_job_not_found"

    @patch("sbo_core.routes.episodic._get_weknora_client")
    def test_get_ingestion_status_weknora_error(self, mock_get_client, client):
        """测试 WeKnora 错误返回 503"""
        from sbo_core.errors import WeKnoraError

        mock_client = AsyncMock()
        mock_client.get_ingestion.side_effect = WeKnoraError(
            error_type="unavailable",
            message="WeKnora service unavailable",
        )
        mock_get_client.return_value = mock_client

        response = client.get("/api/v1/episodic/ingestions/ingest-001")

        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "ingestion_job_failed"
