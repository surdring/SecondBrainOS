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

    health = client.get("/api/v1/health")
    if health.status_code != 200:
        raise RuntimeError(f"health failed status={health.status_code} body={health.text}")

    profile_get = client.get("/api/v1/profile")
    if profile_get.status_code != 200:
        raise RuntimeError(
            f"profile get failed status={profile_get.status_code} body={profile_get.text}"
        )

    profile_put = client.put(
        "/api/v1/profile",
        json={"facts": {"name": "smoke"}, "preferences": {"lang": "zh"}, "constraints": {}},
    )
    if profile_put.status_code != 200:
        raise RuntimeError(
            f"profile put failed status={profile_put.status_code} body={profile_put.text}"
        )

    forget_create = client.post(
        "/api/v1/forget",
        json={"time_range": None, "tags": ["smoke"], "event_ids": []},
    )
    if forget_create.status_code != 200:
        raise RuntimeError(
            f"forget create failed status={forget_create.status_code} body={forget_create.text}"
        )
    erase_job_id = forget_create.json()["erase_job_id"]

    forget_status = client.get(f"/api/v1/forget/{erase_job_id}")
    if forget_status.status_code != 200:
        raise RuntimeError(
            f"forget status failed status={forget_status.status_code} body={forget_status.text}"
        )

    print("OK")


if __name__ == "__main__":
    main()
