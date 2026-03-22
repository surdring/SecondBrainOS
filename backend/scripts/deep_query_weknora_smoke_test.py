from __future__ import annotations

import os
import pathlib

from fastapi.testclient import TestClient

from sbo_core.app import create_app
from sbo_core.database import init_database


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


def _get_db_url() -> str:
    _load_env_file_if_present()
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing required env var: POSTGRES_DSN or DATABASE_URL")
    return dsn


def main() -> None:
    init_database(_get_db_url())
    app = create_app()

    client = TestClient(app)

    payload = {
        "query": "根据文档 SecondBrainOS deep smoke test",
        "mode": "deep",
        "top_k": 5,
        "time_range": None,
        "conversation_id": None,
        "user_id": None,
    }

    resp = client.post("/api/v1/query", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"deep query failed status={resp.status_code} body={resp.text}")

    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("deep query response is not a JSON object")

    if "evidence" not in body:
        raise RuntimeError("deep query response missing evidence")

    if "degraded_services" not in body:
        raise RuntimeError("deep query response missing degraded_services")

    print("OK")


if __name__ == "__main__":
    main()
