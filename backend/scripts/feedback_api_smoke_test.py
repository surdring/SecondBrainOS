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

    # 测试创建反馈
    feedback_create = client.post(
        "/api/v1/feedback",
        json={
            "evidence_id": "smoke-test-evidence-001",
            "feedback_type": "incorrect",
            "user_correction": "正确的内容",
            "query": "测试查询"
        },
    )
    if feedback_create.status_code != 200:
        raise RuntimeError(
            f"feedback create failed status={feedback_create.status_code} body={feedback_create.text}"
        )

    feedback_id = feedback_create.json()["feedback_id"]
    print(f"Created feedback: {feedback_id}")

    # 测试无效反馈类型返回 422
    invalid_feedback = client.post(
        "/api/v1/feedback",
        json={
            "evidence_id": "test",
            "feedback_type": "invalid"
        },
    )
    if invalid_feedback.status_code != 422:
        raise RuntimeError(
            f"expected 422 for invalid feedback_type, got {invalid_feedback.status_code}"
        )

    print("OK")


if __name__ == "__main__":
    main()
