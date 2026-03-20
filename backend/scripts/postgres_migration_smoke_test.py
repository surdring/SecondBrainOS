from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _get_dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing required env var: POSTGRES_DSN or DATABASE_URL")
    return dsn


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")

    dsn = _get_dsn()
    schema = f"sbo_smoke_{uuid.uuid4().hex[:12]}"

    try:
        conn = psycopg.connect(dsn)
    except Exception as e:
        raise RuntimeError(
            "Postgres connection failed. Verify POSTGRES_DSN (user/password/host/port/db) in backend/.env"
        ) from e

    with conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {schema}")

    try:
        os.environ["SBO_DB_SCHEMA"] = schema

        alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", "alembic")

        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

    finally:
        try:
            try:
                conn.close()
            except Exception:
                pass

            conn2 = psycopg.connect(dsn)
            with conn2:
                with conn2.cursor() as cur:
                    cur.execute(f"DROP SCHEMA {schema} CASCADE")
            conn2.close()
        finally:
            os.environ.pop("SBO_DB_SCHEMA", None)


if __name__ == "__main__":
    main()
