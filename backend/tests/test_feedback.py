from __future__ import annotations

import os
import pathlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from sbo_core.app import create_app
from sbo_core.database import init_database, EvidenceFeedback
from sbo_core.models import FeedbackRequest, QueryRequest, QueryMode, Evidence, EvidenceType
from sbo_core.query_service import QueryService


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
    """SQLite file database for testing (file-based to ensure persistence across requests)"""
    db_file = tmp_path / "test.db"
    return f"sqlite:///{db_file}"


@pytest.fixture
def client(sqlite_db_url):
    """创建测试客户端（真实数据库）"""
    init_database(sqlite_db_url)
    app = create_app()
    return TestClient(app)


@pytest.fixture
def query_service(sqlite_db_url):
    """创建 QueryService 实例（真实数据库）"""
    init_database(sqlite_db_url)
    return QueryService()


class TestFeedbackEndpoint:
    """测试 POST /feedback 端点"""

    def test_feedback_create_success(self, client):
        """测试成功创建反馈"""
        request_data = {
            "evidence_id": "test-evidence-123",
            "feedback_type": "incorrect",
            "user_correction": "正确的内容应该是...",
            "session_id": str(uuid.uuid4()),
            "query": "测试查询"
        }

        response = client.post("/api/v1/feedback", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "received"

    def test_feedback_create_invalid_type(self, client):
        """测试无效的反馈类型"""
        request_data = {
            "evidence_id": "test-evidence-123",
            "feedback_type": "invalid_type"
        }

        response = client.post("/api/v1/feedback", json=request_data)

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"

    def test_feedback_create_missing_evidence_id(self, client):
        """测试缺少 evidence_id"""
        request_data = {
            "feedback_type": "incorrect"
        }

        response = client.post("/api/v1/feedback", json=request_data)

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "validation_error"

    def test_feedback_create_success_with_correction(self, client):
        """测试带纠正内容的反馈创建"""
        request_data = {
            "evidence_id": "test-evidence-with-correction",
            "feedback_type": "outdated",
            "user_correction": "这是更新的正确内容",
            "query": "测试查询"
        }

        response = client.post("/api/v1/feedback", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "feedback_id" in data
        assert data["status"] == "received"


class TestFeedbackFiltering:
    """测试反馈过滤策略"""

    @pytest.mark.asyncio
    async def test_feedback_filter_incorrect_evidence(self, query_service, sqlite_db_url, monkeypatch):
        """测试 incorrect 反馈的证据被过滤"""
        from sbo_core.database import get_database

        user_id = "test-user-123"
        evidence_id = "bad-evidence-1"

        # 先插入反馈记录
        db = get_database()
        session = db.get_session()
        try:
            fb = EvidenceFeedback(
                id=uuid.uuid4(),
                user_id=user_id,
                evidence_id=evidence_id,
                feedback_type="incorrect",
                created_at=datetime.now(timezone.utc)
            )
            session.add(fb)
            session.commit()
        finally:
            session.close()

        # Mock retrieval_pipeline 返回包含被标记证据的结果
        async def fake_process(*, query, top_k, mode, time_range, user_id):
            return [
                Evidence(
                    evidence_id=evidence_id,
                    type=EvidenceType.RAW_EVENT,
                    text="被标记为不正确的证据",
                    occurred_at=datetime.now(timezone.utc),
                    source="test",
                    confidence=0.9,
                    refs={}
                ),
                Evidence(
                    evidence_id="good-evidence-1",
                    type=EvidenceType.RAW_EVENT,
                    text="正常的证据",
                    occurred_at=datetime.now(timezone.utc),
                    source="test",
                    confidence=0.9,
                    refs={}
                )
            ], []

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        req = QueryRequest(query="测试", top_k=5, mode=QueryMode.FAST, user_id=user_id)
        resp = await query_service.query(req)

        # 验证被标记的证据被过滤
        evidence_ids = [e.evidence_id for e in resp.evidence]
        assert evidence_id not in evidence_ids
        assert "good-evidence-1" in evidence_ids

    @pytest.mark.asyncio
    async def test_feedback_filter_outdated_evidence(self, query_service, sqlite_db_url, monkeypatch):
        """测试 outdated 反馈的证据被过滤"""
        from sbo_core.database import get_database

        user_id = "test-user-456"
        evidence_id = "old-evidence-1"

        # 先插入 outdated 反馈记录
        db = get_database()
        session = db.get_session()
        try:
            fb = EvidenceFeedback(
                id=uuid.uuid4(),
                user_id=user_id,
                evidence_id=evidence_id,
                feedback_type="outdated",
                created_at=datetime.now(timezone.utc)
            )
            session.add(fb)
            session.commit()
        finally:
            session.close()

        async def fake_process(*, query, top_k, mode, time_range, user_id):
            return [
                Evidence(
                    evidence_id=evidence_id,
                    type=EvidenceType.RAW_EVENT,
                    text="过时的证据",
                    occurred_at=datetime.now(timezone.utc),
                    source="test",
                    confidence=0.8,
                    refs={}
                ),
            ], []

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        req = QueryRequest(query="测试", top_k=5, mode=QueryMode.FAST, user_id=user_id)
        resp = await query_service.query(req)

        evidence_ids = [e.evidence_id for e in resp.evidence]
        assert evidence_id not in evidence_ids

    @pytest.mark.asyncio
    async def test_feedback_filter_incomplete_not_filtered(self, query_service, sqlite_db_url, monkeypatch):
        """测试 incomplete 反馈的证据不被过滤"""
        from sbo_core.database import get_database

        user_id = "test-user-789"
        evidence_id = "incomplete-evidence-1"

        # 插入 incomplete 反馈（不应被过滤）
        db = get_database()
        session = db.get_session()
        try:
            fb = EvidenceFeedback(
                id=uuid.uuid4(),
                user_id=user_id,
                evidence_id=evidence_id,
                feedback_type="incomplete",
                created_at=datetime.now(timezone.utc)
            )
            session.add(fb)
            session.commit()
        finally:
            session.close()

        async def fake_process(*, query, top_k, mode, time_range, user_id):
            return [
                Evidence(
                    evidence_id=evidence_id,
                    type=EvidenceType.RAW_EVENT,
                    text="不完整的证据",
                    occurred_at=datetime.now(timezone.utc),
                    source="test",
                    confidence=0.85,
                    refs={}
                ),
            ], []

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        req = QueryRequest(query="测试", top_k=5, mode=QueryMode.FAST, user_id=user_id)
        resp = await query_service.query(req)

        evidence_ids = [e.evidence_id for e in resp.evidence]
        assert evidence_id in evidence_ids  # incomplete 不应被过滤

    @pytest.mark.asyncio
    async def test_feedback_filter_user_isolation(self, query_service, sqlite_db_url, monkeypatch):
        """测试反馈过滤的用户隔离性"""
        from sbo_core.database import get_database

        user_a = "user-a"
        user_b = "user-b"
        evidence_id = "shared-evidence-1"

        # user_a 标记为 incorrect
        db = get_database()
        session = db.get_session()
        try:
            fb = EvidenceFeedback(
                id=uuid.uuid4(),
                user_id=user_a,
                evidence_id=evidence_id,
                feedback_type="incorrect",
                created_at=datetime.now(timezone.utc)
            )
            session.add(fb)
            session.commit()
        finally:
            session.close()

        async def fake_process(*, query, top_k, mode, time_range, user_id):
            return [
                Evidence(
                    evidence_id=evidence_id,
                    type=EvidenceType.RAW_EVENT,
                    text="共享证据",
                    occurred_at=datetime.now(timezone.utc),
                    source="test",
                    confidence=0.9,
                    refs={}
                ),
            ], []

        monkeypatch.setattr("sbo_core.query_service.retrieval_pipeline.process", fake_process)

        # user_a 查询应过滤
        req_a = QueryRequest(query="测试", top_k=5, mode=QueryMode.FAST, user_id=user_a)
        resp_a = await query_service.query(req_a)
        assert evidence_id not in [e.evidence_id for e in resp_a.evidence]

        # user_b 查询不应过滤
        req_b = QueryRequest(query="测试", top_k=5, mode=QueryMode.FAST, user_id=user_b)
        resp_b = await query_service.query(req_b)
        assert evidence_id in [e.evidence_id for e in resp_b.evidence]
