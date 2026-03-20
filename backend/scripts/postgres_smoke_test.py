from __future__ import annotations

import os
from pathlib import Path

import psycopg


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


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing required env var: POSTGRES_DSN or DATABASE_URL")

    try:
        conn = psycopg.connect(dsn)
    except Exception as e:
        raise RuntimeError(
            "Postgres connection failed. Verify POSTGRES_DSN (user/password/host/port/db) in backend/.env"
        ) from e

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            one = cur.fetchone()
            if not one or one[0] != 1:
                raise RuntimeError("Postgres basic query failed")

            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
            if not row:
                raise RuntimeError("pgvector extension not found (expected extension name: vector)")


if __name__ == "__main__":
    main()
