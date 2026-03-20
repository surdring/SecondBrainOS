from __future__ import annotations

import os
import uuid

import psycopg
from psycopg import sql
import pytest
from alembic import command
from alembic.config import Config


def _get_dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing required env var: POSTGRES_DSN or DATABASE_URL")
    return dsn


@pytest.fixture()
def temp_schema(env_base: None, monkeypatch: pytest.MonkeyPatch) -> str:
    schema = f"sbo_test_{uuid.uuid4().hex[:12]}"

    conn = psycopg.connect(_get_dsn())
    with conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {schema}")

    monkeypatch.setenv("SBO_DB_SCHEMA", schema)

    try:
        yield schema
    finally:
        try:
            try:
                conn.close()
            except Exception:
                pass

            conn2 = psycopg.connect(_get_dsn())
            with conn2:
                with conn2.cursor() as cur:
                    cur.execute(f"DROP SCHEMA {schema} CASCADE")
            conn2.close()
        except Exception:
            pass


def _alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    return cfg


def _expect_error_with_savepoint(
    cur: psycopg.Cursor,
    exc_type: type[BaseException],
    stmt: sql.SQL,
    params: tuple[object, ...] | None = None,
) -> None:
    cur.execute("SAVEPOINT sp")
    try:
        if params is None:
            cur.execute(stmt)
        else:
            cur.execute(stmt, params)
    except exc_type:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
    else:
        raise AssertionError(f"Expected exception {exc_type.__name__} was not raised")
    finally:
        cur.execute("RELEASE SAVEPOINT sp")


def test_migrations_upgrade_downgrade_upgrade(temp_schema: str) -> None:
    cfg = _alembic_cfg()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_raw_events_unique_constraints(temp_schema: str) -> None:
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    conn_check = psycopg.connect(_get_dsn())
    with conn_check:
        with conn_check.cursor() as cur:
            cur.execute(
                "SELECT table_schema FROM information_schema.tables WHERE table_name = 'raw_events' ORDER BY table_schema"
            )
            schemas = [row[0] for row in cur.fetchall()]
    conn_check.close()
    assert temp_schema in schemas

    conn = psycopg.connect(_get_dsn())
    with conn:
        with conn.cursor() as cur:
            insert_ok = sql.SQL(
                """
                INSERT INTO {}.raw_events (source, source_message_id, idempotency_key, content, occurred_at, metadata)
                VALUES ('web', 'msg-1', 'idem-1', 'hello', NOW(), '{{}}'::jsonb)
                RETURNING event_id
                """
            ).format(sql.Identifier(temp_schema))
            cur.execute(insert_ok)
            _ = cur.fetchone()

            insert_dup_source = sql.SQL(
                """
                INSERT INTO {}.raw_events (source, source_message_id, idempotency_key, content, occurred_at)
                VALUES ('web', 'msg-1', 'idem-2', 'dup source message', NOW())
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.UniqueViolation, insert_dup_source)

            insert_dup_idem = sql.SQL(
                """
                INSERT INTO {}.raw_events (source, source_message_id, idempotency_key, content, occurred_at)
                VALUES ('telegram', 'msg-2', 'idem-1', 'dup idem', NOW())
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.UniqueViolation, insert_dup_idem)


def test_extractions_confidence_range_constraint(temp_schema: str) -> None:
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    conn = psycopg.connect(_get_dsn())
    with conn:
        with conn.cursor() as cur:
            insert_event = sql.SQL(
                """
                INSERT INTO {}.raw_events (source, content, occurred_at)
                VALUES ('web', 'hello', NOW())
                RETURNING event_id
                """
            ).format(sql.Identifier(temp_schema))
            cur.execute(insert_event)
            event_id = cur.fetchone()[0]

            insert_bad = sql.SQL(
                """
                INSERT INTO {}.extractions (event_id, extraction_type, content, confidence)
                VALUES (%s, 'fact', '{{}}'::jsonb, 1.5)
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.CheckViolation, insert_bad, (event_id,))


def test_erase_jobs_status_and_items_constraints(temp_schema: str) -> None:
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    conn = psycopg.connect(_get_dsn())
    with conn:
        with conn.cursor() as cur:
            insert_job_bad_status = sql.SQL(
                """
                INSERT INTO {}.erase_jobs (status, request)
                VALUES ('bad', '{{}}'::jsonb)
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.CheckViolation, insert_job_bad_status)

            cur.execute(
                sql.SQL(
                    """
                    INSERT INTO {}.erase_jobs (status, request)
                    VALUES ('queued', '{{}}'::jsonb)
                    RETURNING erase_job_id
                    """
                ).format(sql.Identifier(temp_schema))
            )
            erase_job_id = cur.fetchone()[0]

            insert_item_bad_action = sql.SQL(
                """
                INSERT INTO {}.erase_job_items (erase_job_id, action, status)
                VALUES (%s, 'bad', 'queued')
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.CheckViolation, insert_item_bad_action, (erase_job_id,))

            insert_item_bad_status = sql.SQL(
                """
                INSERT INTO {}.erase_job_items (erase_job_id, action, status)
                VALUES (%s, 'soft_delete', 'bad')
                """
            ).format(sql.Identifier(temp_schema))
            _expect_error_with_savepoint(cur, psycopg.errors.CheckViolation, insert_item_bad_status, (erase_job_id,))
