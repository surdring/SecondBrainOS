"""add evidence_feedback table

Revision ID: 0002_add_evidence_feedback
Revises: 0001_init_core_tables
Create Date: 2026-03-21

"""

from __future__ import annotations

import os
import re

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_add_evidence_feedback"
down_revision = "0001_init_core_tables"
branch_labels = None
depends_on = None


_SCHEMA_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS %sevidence_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NULL,
            evidence_id TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            user_correction TEXT NULL,
            session_id TEXT NULL,
            query TEXT NULL,
            payload JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
        % prefix
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_feedback_user_created_at ON %sevidence_feedback (user_id, created_at DESC)"
        % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_feedback_evidence_id ON %sevidence_feedback (evidence_id)" % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_feedback_feedback_type ON %sevidence_feedback (feedback_type)" % prefix
    )


def downgrade() -> None:
    schema = _get_schema()
    prefix = f"{schema}."
    op.execute("DROP TABLE IF EXISTS %sevidence_feedback" % prefix)
