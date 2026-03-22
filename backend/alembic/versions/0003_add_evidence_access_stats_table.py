"""add evidence_access_stats table

Revision ID: 0003_add_evidence_access_stats
Revises: 0002_add_evidence_feedback
Create Date: 2026-03-22

"""

from __future__ import annotations

import os
import re

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_evidence_access_stats"
down_revision = "0002_add_evidence_feedback"
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
        CREATE TABLE IF NOT EXISTS %sevidence_access_stats (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
        % prefix
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_access_stats_user_evidence ON %sevidence_access_stats (user_id, evidence_id)"
        % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_access_stats_user_last_accessed_at ON %sevidence_access_stats (user_id, last_accessed_at DESC)"
        % prefix
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_access_stats_evidence_id ON %sevidence_access_stats (evidence_id)" % prefix
    )


def downgrade() -> None:
    schema = _get_schema()
    prefix = f"{schema}."
    op.execute("DROP TABLE IF EXISTS %sevidence_access_stats" % prefix)
