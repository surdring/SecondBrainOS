from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
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


def _run_migrations(*, schema: str) -> None:
    os.environ["SBO_DB_SCHEMA"] = schema

    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )

    command.upgrade(alembic_cfg, "head")


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")
    dsn = _get_dsn()

    schema = f"sbo_smoke_access_{uuid.uuid4().hex[:12]}"

    try:
        conn = psycopg.connect(dsn)
    except Exception as e:
        raise RuntimeError(
            "Postgres connection failed. Verify POSTGRES_DSN (user/password/host/port/db) in backend/.env"
        ) from e

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA {schema}")

        _run_migrations(schema=schema)

        try:
            conn.close()
        except Exception:
            pass

        conn = psycopg.connect(dsn)

        user_id = "smoke_u1"
        evidence_id = "e1"
        ts1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {schema}.evidence_access_stats (id, user_id, evidence_id, access_count, last_accessed_at)
                    VALUES (gen_random_uuid(), %s, %s, 1, %s)
                    """,
                    (user_id, evidence_id, ts1),
                )

                cur.execute(
                    f"""
                    UPDATE {schema}.evidence_access_stats
                    SET access_count = access_count + 1,
                        last_accessed_at = %s
                    WHERE user_id = %s AND evidence_id = %s
                    """,
                    (ts2, user_id, evidence_id),
                )

                cur.execute(
                    f"""
                    SELECT access_count, last_accessed_at
                    FROM {schema}.evidence_access_stats
                    WHERE user_id = %s AND evidence_id = %s
                    """,
                    (user_id, evidence_id),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Missing evidence_access_stats row")

                access_count, last_accessed_at = row
                if int(access_count) != 2:
                    raise RuntimeError(f"Unexpected access_count: {access_count} (expected 2)")
                if last_accessed_at != ts2:
                    raise RuntimeError(
                        f"Unexpected last_accessed_at: {last_accessed_at!r} (expected {ts2!r})"
                    )

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
