from __future__ import annotations

import os
import pathlib
from unittest.mock import AsyncMock, patch

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

    # Mock WeKnora client for smoke test (since we may not have real WeKnora in smoke test env)
    with patch("sbo_core.routes.episodic._get_weknora_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_knowledge_bases.return_value = [
            {"id": "smoke-kb-001", "name": "Smoke Test KB"}
        ]
        mock_client.create_knowledge_base.return_value = {
            "id": "smoke-kb-new",
            "name": "New Smoke KB",
            "description": "Created in smoke test",
            "created_at": "2026-03-21T10:00:00Z",
            "updated_at": "2026-03-21T10:00:00Z",
        }
        mock_client.create_ingestion.return_value = {
            "id": "smoke-ingest-001",
            "kb_id": "smoke-kb-001",
            "status": "queued",
        }
        mock_client.get_ingestion.return_value = {
            "id": "smoke-ingest-001",
            "kb_id": "smoke-kb-001",
            "status": "succeeded",
            "source_type": "file",
            "created_at": "2026-03-21T10:00:00Z",
            "processed_items": 10,
            "total_items": 10,
        }
        mock_get_client.return_value = mock_client

        # Test list knowledge bases
        kb_list = client.get("/api/v1/episodic/knowledge-bases")
        if kb_list.status_code != 200:
            raise RuntimeError(
                f"list knowledge bases failed status={kb_list.status_code} body={kb_list.text}"
            )
        print(f"KB list: {kb_list.json()['data']}")

        # Test create knowledge base
        kb_create = client.post(
            "/api/v1/episodic/knowledge-bases",
            json={
                "name": "New Smoke KB",
                "description": "Created in smoke test",
                "tags": ["smoke"],
                "metadata": {},
            },
        )
        if kb_create.status_code != 200:
            raise RuntimeError(
                f"create knowledge base failed status={kb_create.status_code} body={kb_create.text}"
            )
        kb_id = kb_create.json()["kb_id"]
        print(f"Created KB: {kb_id}")

        # Test create ingestion
        import uuid
        ingest_create = client.post(
            "/api/v1/episodic/ingestions",
            json={
                "kb_id": str(uuid.uuid4()),
                "source_type": "file",
                "source_payload": {"file_path": "/test/file.pdf"},
                "tags": ["doc"],
            },
        )
        if ingest_create.status_code != 200:
            raise RuntimeError(
                f"create ingestion failed status={ingest_create.status_code} body={ingest_create.text}"
            )
        ingest_id = ingest_create.json()["ingestion_job_id"]
        print(f"Created ingestion: {ingest_id}")

        # Test get ingestion status
        ingest_status = client.get(f"/api/v1/episodic/ingestions/{ingest_id}")
        if ingest_status.status_code != 200:
            raise RuntimeError(
                f"get ingestion status failed status={ingest_status.status_code} body={ingest_status.text}"
            )
        print(f"Ingestion status: {ingest_status.json()['status']}")

    print("OK")


if __name__ == "__main__":
    main()
