"""
Create pending_profile_changes table for user confirmation mechanism

Revision ID: 0006_add_pending_profile_changes
Revises: 0005_add_embedding_error_fields
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = '0006_add_pending_profile_changes'
down_revision = '0005_add_embedding_error_fields'
branch_labels = None
depends_on = None


def upgrade():
    schema = op.get_context().connection.dialect.default_schema_name
    
    # 创建 pending_profile_changes 表
    op.create_table(
        'pending_profile_changes',
        sa.Column('change_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('field_type', sa.String(50), nullable=False),
        sa.Column('field_key', sa.String(100), nullable=False),
        sa.Column('old_value', postgresql.JSONB(), nullable=True),
        sa.Column('new_value', postgresql.JSONB(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, default=0.0),
        sa.Column('source_extraction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_reason', sa.Text(), nullable=True),
        schema=schema,
    )
    
    # 创建索引
    op.create_index(
        'ix_pending_profile_changes_user_status',
        'pending_profile_changes',
        ['user_id', 'status'],
        schema=schema
    )
    
    op.create_index(
        'ix_pending_profile_changes_created_at',
        'pending_profile_changes',
        ['created_at'],
        schema=schema
    )


def downgrade():
    schema = op.get_context().connection.dialect.default_schema_name
    
    # 删除表
    op.drop_table('pending_profile_changes', schema=schema)
