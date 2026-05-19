"""
Add error_type and retry_priority to embeddings table
Add conversation_id to ingestion_jobs table

Revision ID: 0005_add_embedding_error_fields
Revises: 0004_add_embeddings_table
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = '0005_add_embedding_error_fields'
down_revision = '0004_add_embeddings_table'
branch_labels = None
depends_on = None


def upgrade():
    schema = op.get_context().connection.dialect.default_schema_name
    
    # 添加 error_type 字段到 embeddings 表
    op.add_column(
        'embeddings',
        sa.Column('error_type', sa.String(50), nullable=True),
        schema=schema
    )
    
    # 添加 retry_priority 字段到 embeddings 表
    op.add_column(
        'embeddings',
        sa.Column('retry_priority', sa.String(20), nullable=True),
        schema=schema
    )
    
    # 为 error_type 添加索引
    op.create_index(
        'ix_embeddings_error_type',
        'embeddings',
        ['error_type'],
        schema=schema
    )
    
    # 为 retry_priority 添加索引
    op.create_index(
        'ix_embeddings_retry_priority',
        'embeddings',
        ['retry_priority'],
        schema=schema
    )
    
    # 添加 conversation_id 字段到 ingestion_jobs 表
    op.add_column(
        'ingestion_jobs',
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema=schema
    )
    
    # 为 conversation_id 添加索引
    op.create_index(
        'ix_ingestion_jobs_conversation_id',
        'ingestion_jobs',
        ['conversation_id'],
        schema=schema
    )
    
    # 添加唯一约束（conversation_id + source_type），用于幂等性检查
    op.create_unique_constraint(
        'uq_ingestion_jobs_conv_source',
        'ingestion_jobs',
        ['conversation_id', 'source_type'],
        schema=schema
    )


def downgrade():
    schema = op.get_context().connection.dialect.default_schema_name
    
    # 删除约束
    op.drop_constraint('uq_ingestion_jobs_conv_source', 'ingestion_jobs', schema=schema)
    
    # 删除索引
    op.drop_index('ix_embeddings_retry_priority', table_name='embeddings', schema=schema)
    op.drop_index('ix_embeddings_error_type', table_name='embeddings', schema=schema)
    op.drop_index('ix_ingestion_jobs_conversation_id', table_name='ingestion_jobs', schema=schema)
    
    # 删除字段
    op.drop_column('embeddings', 'retry_priority', schema=schema)
    op.drop_column('embeddings', 'error_type', schema=schema)
    op.drop_column('ingestion_jobs', 'conversation_id', schema=schema)
