"""Initial database schema for Aegra Agent Protocol tables

Revision ID: 0001
Revises: 
Create Date: 2025-08-17 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250817160000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create uuid-ossp extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    
    # Create assistant table
    op.create_table('assistant',
        sa.Column('assistant_id', sa.Text(), nullable=False, server_default=sa.text("uuid_generate_v4()::text")),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('graph_id', sa.Text(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint('assistant_id')
    )
    
    # Create thread table (before runs since runs references thread)
    op.create_table('thread',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'idle'")),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint('thread_id')
    )
    
    # Create runs table (after assistant and thread since it references both)
    op.create_table('runs',
        sa.Column('run_id', sa.Text(), nullable=False, server_default=sa.text("uuid_generate_v4()::text")),
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('assistant_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(['assistant_id'], ['assistant.assistant_id'], ),
        sa.ForeignKeyConstraint(['thread_id'], ['thread.thread_id'], ),
        sa.PrimaryKeyConstraint('run_id')
    )
    
    # Note: run_events table is not defined in current models
    
    # Create indexes for performance
    op.create_index('idx_assistant_user', 'assistant', ['user_id'], unique=False)
    op.create_index('idx_assistant_user_graph', 'assistant', ['user_id', 'graph_id'], unique=True)
    op.create_index('idx_runs_thread_id', 'runs', ['thread_id'], unique=False)
    op.create_index('idx_runs_user', 'runs', ['user_id'], unique=False)
    op.create_index('idx_runs_status', 'runs', ['status'], unique=False)
    op.create_index('idx_runs_assistant_id', 'runs', ['assistant_id'], unique=False)
    op.create_index('idx_runs_created_at', 'runs', ['created_at'], unique=False)
    op.create_index('idx_thread_user', 'thread', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_thread_user', table_name='thread')
    op.drop_index('idx_runs_created_at', table_name='runs')
    op.drop_index('idx_runs_assistant_id', table_name='runs')
    op.drop_index('idx_runs_status', table_name='runs')
    op.drop_index('idx_runs_user', table_name='runs')
    op.drop_index('idx_runs_thread_id', table_name='runs')
    op.drop_index('idx_assistant_user', table_name='assistant')
    op.drop_index('idx_assistant_user_graph', table_name='assistant')
    
    # Drop tables
    op.drop_table('thread')
    op.drop_table('runs')
    op.drop_table('assistant')
