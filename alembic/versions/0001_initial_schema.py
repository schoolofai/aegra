"""Initial database schema for Aegra Agent Protocol tables

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create uuid-ossp extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    
    # Create assistant table
    op.create_table('assistant',
        sa.Column('assistant_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('graph_id', sa.Text(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('assistant_id')
    )
    
    # Create runs table
    op.create_table('runs',
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('assistant_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assistant_id'], ['assistant.assistant_id'], ),
        sa.PrimaryKeyConstraint('run_id')
    )
    
    # Create thread table
    op.create_table('thread',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('thread_id')
    )
    
    # Create run_events table for SSE replay persistence
    op.create_table('run_events',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('event', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_assistant_user_graph', 'assistant', ['user_id', 'graph_id'], unique=True)
    op.create_index('idx_assistant_user', 'assistant', ['user_id'], unique=False)
    op.create_index('idx_runs_thread_id', 'runs', ['thread_id'], unique=False)
    op.create_index('idx_runs_user', 'runs', ['user_id'], unique=False)
    op.create_index('idx_runs_status', 'runs', ['status'], unique=False)
    op.create_index('idx_runs_assistant_id', 'runs', ['assistant_id'], unique=False)
    op.create_index('idx_runs_created_at', 'runs', ['created_at'], unique=False)
    op.create_index('idx_thread_user', 'thread', ['user_id'], unique=False)
    op.create_index('idx_run_events_run_seq', 'run_events', ['run_id', 'seq'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_run_events_run_seq', table_name='run_events')
    op.drop_index('idx_thread_user', table_name='thread')
    op.drop_index('idx_runs_created_at', table_name='runs')
    op.drop_index('idx_runs_assistant_id', table_name='runs')
    op.drop_index('idx_runs_status', table_name='runs')
    op.drop_index('idx_runs_user', table_name='runs')
    op.drop_index('idx_runs_thread_id', table_name='runs')
    op.drop_index('idx_assistant_user', table_name='assistant')
    op.drop_index('idx_assistant_user_graph', table_name='assistant')
    
    # Drop tables
    op.drop_table('run_events')
    op.drop_table('thread')
    op.drop_table('runs')
    op.drop_table('assistant')
