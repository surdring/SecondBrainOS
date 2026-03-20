from __future__ import annotations

from fastapi.testclient import TestClient

from sbo_core.app import create_app


def test_request_id_is_generated_and_returned() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    request_id = resp.headers.get("X-Request-ID")
    assert isinstance(request_id, str)
    assert request_id


def test_request_id_is_propagated() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/health", headers={"X-Request-ID": "test-request-id"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "test-request-id"


def test_http_error_is_structured() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/path-not-exist")
    assert resp.status_code == 404

    data = resp.json()
    assert isinstance(data, dict)
    assert data.get("code") == "http_error"
    assert isinstance(data.get("message"), str)
    assert isinstance(data.get("request_id"), str)
    assert resp.headers.get("X-Request-ID") == data.get("request_id")
