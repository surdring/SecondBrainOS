from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from uuid import UUID

from sbo_core.app import create_app


@pytest.fixture
def client(monkeypatch):
    from sbo_core.database import init_database

    # 用 sqlite 内存库替代 postgres，避免单测依赖外部服务
    init_database("sqlite:///:memory:")
    app = create_app()
    return TestClient(app)


def test_health_ok(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "dependencies" in body
    assert "queue" in body
    assert "postgres" in body["dependencies"]
    assert "redis" in body["dependencies"]
    assert "neo4j" in body["dependencies"]


def test_profile_get_and_put_roundtrip(client: TestClient):
    get_resp = client.get("/api/v1/profile")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "user_id" in data

    put_resp = client.put(
        "/api/v1/profile",
        json={"facts": {"name": "alice"}, "preferences": {"lang": "zh"}, "constraints": {"region": "cn"}},
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["facts"]["name"] == "alice"


def test_forget_create_and_status(client: TestClient):
    create_resp = client.post(
        "/api/v1/forget",
        json={
            "time_range": {"start": "2026-03-20T00:00:00+00:00", "end": "2026-03-21T00:00:00+00:00"},
            "tags": ["t"],
            "event_ids": [],
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["erase_job_id"]

    status_resp = client.get(f"/api/v1/forget/{job_id}")
    assert status_resp.status_code == 200
    payload = status_resp.json()
    assert payload["erase_job_id"] == job_id
    assert payload["status"] == "queued"


def test_forget_status_not_found(client: TestClient):
    missing_id = "00000000-0000-0000-0000-000000000001"
    resp = client.get(f"/api/v1/forget/{missing_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "erase_job_not_found"
