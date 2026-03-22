from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from sbo_core.app import create_app
from sbo_core.database import init_database
from sbo_core.retrieval_pipeline import RetrievalPipeline


@pytest.fixture
def client() -> TestClient:
    init_database("sqlite:///:memory:")
    app = create_app()
    return TestClient(app)


def test_manage_forget_emits_audit_log(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="sbo_core")

    resp = client.post(
        "/api/v1/forget",
        json={"time_range": None, "tags": ["audit"], "event_ids": []},
    )
    assert resp.status_code == 200

    records = [r for r in caplog.records if r.getMessage() == "audit"]
    assert records, "expected at least one audit log record"

    matched = False
    for r in records:
        if getattr(r, "audit_event", None) == "forget.create" and getattr(r, "audit_outcome", None) == "success":
            details = getattr(r, "audit_details", None)
            assert isinstance(details, dict)
            assert details.get("erase_job_id")
            matched = True
            break
    assert matched, "expected forget.create success audit log"


@pytest.mark.asyncio
async def test_weknora_recall_emits_audit_log_success(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from sbo_core.degradation import DegradationStrategy

    pipeline = RetrievalPipeline()

    monkeypatch.setenv("WEKNORA_ENABLE", "true")
    monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.local/api/v1")
    monkeypatch.setenv("WEKNORA_API_KEY", "test")
    monkeypatch.setenv("WEKNORA_REQUEST_TIMEOUT_MS", "10000")
    monkeypatch.setenv("WEKNORA_RETRIEVAL_TOP_K", "8")
    monkeypatch.setenv("WEKNORA_RETRIEVAL_THRESHOLD", "")
    monkeypatch.setenv("WEKNORA_TIME_DECAY_RATE", "0.1")
    monkeypatch.setenv("WEKNORA_SEMANTIC_WEIGHT", "0.7")
    monkeypatch.setenv("WEKNORA_TIME_WEIGHT", "0.3")
    monkeypatch.setenv("WEKNORA_DEGRADATION_STRATEGY", DegradationStrategy.FAIL.value)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/knowledge-search"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {
                            "id": "chunk-1",
                            "content": "hello",
                            "score": 0.9,
                            "knowledge_id": "k1",
                            "knowledge_title": "t1",
                            "chunk_index": 0,
                            "metadata": {"occurred_at": "2026-03-21T00:00:00+00:00"},
                        }
                    ],
                },
            )
        return httpx.Response(404, json={"success": False})

    pipeline._weknora_transport = httpx.MockTransport(handler)

    caplog.set_level(logging.INFO, logger="sbo_core")
    degraded: list[str] = []
    _ = await pipeline._episodic_recall("q", None, None, degraded)

    records = [r for r in caplog.records if r.getMessage() == "audit"]
    assert records, "expected at least one audit log record"

    matched = False
    for r in records:
        if getattr(r, "audit_event", None) == "weknora.recall" and getattr(r, "audit_outcome", None) == "success":
            details = getattr(r, "audit_details", None)
            assert isinstance(details, dict)
            assert details.get("candidates_out") == 1
            matched = True
            break
    assert matched, "expected weknora.recall success audit log"
