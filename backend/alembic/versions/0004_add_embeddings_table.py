"""add embeddings table

Revision ID: 0004_add_embeddings_table
Revises: 0003_add_evidence_access_stats_table
Create Date: 2026-03-22

"""

from __future__ import annotations

import os
import re
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_add_embeddings_table"
down_revision = "0003_add_evidence_access_stats_table"
branch_labels = None
depends_on = None


_SCHEMA_RE = re.compile(r"^[a-zA_][a-zA-Z0-9_]*$")
_logger = logging.getLogger("alembic.revision.0004")


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

    _logger.info("Creating embeddings table in schema=%s", schema)

    # 创建 embeddings 表
    op.create_table(
        "embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False, index=True, unique=True),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),  # 存储为 JSONB，实际向量使用 pgvector
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.text("now()")),
        # 重跑审计字段
        sa.Column("rerun_count", sa.Integer(), default=0),
        sa.Column("last_rerun_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        schema=schema,
    )

    # 添加外键约束（引用 raw_events）
    op.create_foreign_key(
        "fk_embeddings_raw_events",
        "embeddings",
        "raw_events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
        source_schema=schema,
        referent_schema=schema,
    )

    # 创建索引
    op.create_index(
        "ix_embeddings_event_id",
        "embeddings",
        ["event_id"],
        schema=schema,
    )
    op.create_index(
        "ix_embeddings_model_name",
        "embeddings",
        ["model_name"],
        schema=schema,
    )
    op.create_index(
        "ix_embeddings_created_at",
        "embeddings",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_embeddings_error_message",
        "embeddings",
        ["error_message"],
        postgresql_where=sa.text("error_message IS NOT NULL"),
        schema=schema,
    )

    # 添加注释
    op.execute(
        f"""
        COMMENT ON TABLE {prefix}embeddings IS 
        '向量嵌入表 - 存储事件的向量表示，支持失败重跑和审计'
        """
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {prefix}embeddings.embedding IS 
        '向量数据（JSONB格式），实际使用pgvector时可通过raw SQL操作vector类型'
        """
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {prefix}embeddings.rerun_count IS 
        '重跑次数，用于审计和追踪'
        """
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {prefix}embeddings.error_message IS 
        '上次失败原因，用于后续重跑识别'
        """
    )

    _logger.info("embeddings table created successfully")


def downgrade() -> None:
    schema = _get_schema()

    _logger.info("Dropping embeddings table from schema=%s", schema)

    # 删除索引
    op.drop_index("ix_embeddings_error_message", table_name="embeddings", schema=schema)
    op.drop_index("ix_embeddings_created_at", table_name="embeddings", schema=schema)
    op.drop_index("ix_embeddings_model_name", table_name="embeddings", schema=schema)
    op.drop_index("ix_embeddings_event_id", table_name="embeddings", schema=schema)

    # 删除外键约束
    op.drop_constraint("fk_embeddings_raw_events", "embeddings", schema=schema)

    # 删除表
    op.drop_table("embeddings", schema=schema)

    _logger.info("embeddings table dropped successfully")
