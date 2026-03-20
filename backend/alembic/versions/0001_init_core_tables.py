"""init core tables

Revision ID: 0001_init_core_tables
Revises: 
Create Date: 2026-03-20

"""

from __future__ import annotations

import os
import re
import logging

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_init_core_tables"
down_revision = None
branch_labels = None
depends_on = None


_SCHEMA_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_logger = logging.getLogger("alembic.revision.0001")


def _get_schema() -> str:
    schema = os.environ.get("SBO_DB_SCHEMA", "public")
    if not schema:
        return "public"
    if not _SCHEMA_RE.match(schema):
        raise RuntimeError("Invalid SBO_DB_SCHEMA")
    return schema


def upgrade() -> None:
    schema = _get_schema()
    prefix = f"{schema}."

    bind = op.get_bind()
    try:
        db = bind.exec_driver_sql("SELECT current_database()").scalar_one()
        sch = bind.exec_driver_sql("SELECT current_schema()").scalar_one()
        sp = bind.exec_driver_sql("SHOW search_path").scalar_one()
        _logger.info("upgrade_context db=%s schema=%s search_path=%s target_schema=%s", db, sch, sp, schema)
    except Exception as e:
        _logger.warning("upgrade_context_probe_failed: %r", e)

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %sraw_events (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NULL,
            source TEXT NOT NULL,
            source_message_id TEXT NULL,
            idempotency_key TEXT NULL,
            content TEXT NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NULL,
            deleted_at TIMESTAMPTZ NULL
        )
        """ % prefix
    )

    try:
        exists = bind.exec_driver_sql(f"SELECT to_regclass('{schema}.raw_events')").scalar_one()
        _logger.info("post_create_raw_events to_regclass=%s", exists)
    except Exception as e:
        _logger.warning("post_create_raw_events_probe_failed: %r", e)

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_events_occurred_at ON %sraw_events (occurred_at DESC)" % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_events_user_occurred_at ON %sraw_events (user_id, occurred_at DESC)" % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_events_not_deleted ON %sraw_events (event_id) WHERE deleted_at IS NULL" % prefix
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_events_idempotency_key ON %sraw_events (idempotency_key) WHERE idempotency_key IS NOT NULL"
        % prefix
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_events_source_message_id ON %sraw_events (source, source_message_id) WHERE source_message_id IS NOT NULL"
        % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %sextractions (
            extraction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES %sraw_events(event_id) ON DELETE CASCADE,
            extraction_type TEXT NOT NULL,
            content JSONB NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_extractions_confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0)
        )
        """ % (prefix, prefix)
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_extractions_event_id ON %sextractions (event_id)" % prefix)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_extractions_type_created_at ON %sextractions (extraction_type, created_at DESC)"
        % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %suser_profiles (
            user_id TEXT PRIMARY KEY,
            profile JSONB NOT NULL,
            version INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """ % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %suser_profile_versions (
            profile_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL REFERENCES %suser_profiles(user_id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            profile JSONB NOT NULL,
            reason TEXT NULL,
            source_extraction_id UUID NULL REFERENCES %sextractions(extraction_id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """ % (prefix, prefix, prefix)
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_profile_versions_user_version ON %suser_profile_versions (user_id, version)"
        % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %sembeddings (
            embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES %sraw_events(event_id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """ % (prefix, prefix)
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_embeddings_event_id ON %sembeddings (event_id)" % prefix)
    op.execute("CREATE INDEX IF NOT EXISTS ix_embeddings_created_at ON %sembeddings (created_at DESC)" % prefix)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_embedding_ivfflat ON %sembeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %serase_jobs (
            erase_job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NULL,
            status TEXT NOT NULL,
            request JSONB NOT NULL,
            summary JSONB NULL,
            error_message TEXT NULL,
            queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            CONSTRAINT ck_erase_jobs_status CHECK (status IN ('queued','running','succeeded','failed'))
        )
        """ % prefix
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_erase_jobs_status_queued_at ON %serase_jobs (status, queued_at DESC)" % prefix
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %serase_job_items (
            erase_job_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erase_job_id UUID NOT NULL REFERENCES %serase_jobs(erase_job_id) ON DELETE CASCADE,
            event_id UUID NULL REFERENCES %sraw_events(event_id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_erase_job_items_action CHECK (action IN ('soft_delete','hard_delete')),
            CONSTRAINT ck_erase_job_items_status CHECK (status IN ('queued','running','succeeded','failed'))
        )
        """ % (prefix, prefix, prefix)
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_erase_job_items_job_id ON %serase_job_items (erase_job_id)" % prefix)


def downgrade() -> None:
    schema = _get_schema()
    prefix = f"{schema}."

    op.execute("DROP TABLE IF EXISTS %serase_job_items" % prefix)
    op.execute("DROP TABLE IF EXISTS %serase_jobs" % prefix)
    op.execute("DROP TABLE IF EXISTS %sembeddings" % prefix)
    op.execute("DROP TABLE IF EXISTS %suser_profile_versions" % prefix)
    op.execute("DROP TABLE IF EXISTS %suser_profiles" % prefix)
    op.execute("DROP TABLE IF EXISTS %sextractions" % prefix)
    op.execute("DROP TABLE IF EXISTS %sraw_events" % prefix)
