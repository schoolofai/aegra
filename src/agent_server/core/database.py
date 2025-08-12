"""Database manager with LangGraph integration"""
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import text
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore


class DatabaseManager:
    """Manages database connections and LangGraph persistence components"""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self._checkpointer: Optional[AsyncPostgresSaver] = None
        self._checkpointer_cm = None  # holds the contextmanager so we can close it
        self._store: Optional[AsyncPostgresStore] = None
        self._store_cm = None
        self._database_url = os.getenv(
            "DATABASE_URL", 
            "postgresql+asyncpg://user:password@localhost:5432/aegra"
        )
    
    async def initialize(self):
        """Initialize database connections and LangGraph components"""
        # SQLAlchemy for our minimal Agent Protocol metadata tables
        self.engine = create_async_engine(
            self._database_url,
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true"
        )
        
        # Convert asyncpg URL to psycopg format for LangGraph
        # LangGraph packages require psycopg format, not asyncpg
        dsn = self._database_url.replace("postgresql+asyncpg://", "postgresql://")
        
        # Store connection string for creating LangGraph components on demand
        self._langgraph_dsn = dsn
        self.checkpointer = None
        self.store = None
        # Note: LangGraph components will be created as context managers when needed
        
        # Create our minimal metadata tables
        await self._create_metadata_tables()
        
        print("✅ Database and LangGraph components initialized")
    
    async def _create_metadata_tables(self):
        """Create Agent Protocol metadata tables"""
        async with self.engine.begin() as conn:
            # Ensure required extension for UUID generation-as-text BEFORE using uuid_generate_v4()
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))

            # Create tables one by one (asyncpg doesn't support multiple statements)
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistant (
                    assistant_id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
                    name TEXT NOT NULL,
                    description TEXT,
                    graph_id TEXT NOT NULL,
                    config JSONB DEFAULT '{}',
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
                    thread_id TEXT NOT NULL,
                    assistant_id TEXT REFERENCES assistant(assistant_id),
                    status TEXT DEFAULT 'pending',
                    input JSONB,
                    config JSONB,
                    output JSONB,
                    error_message TEXT,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS thread (
                    thread_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'idle',
                    metadata_json JSONB DEFAULT '{}',
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))

            # Events table for SSE replay persistence
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create indexes
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_user_graph ON assistant(user_id, graph_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_assistant_user ON assistant(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_assistant_id ON runs(assistant_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_thread_user ON thread(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_run_events_run_seq ON run_events(run_id, seq)"))
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

        # Close the cached checkpointer if we opened one
        if self._checkpointer_cm is not None:
            await self._checkpointer_cm.__aexit__(None, None, None)
            self._checkpointer_cm = None
            self._checkpointer = None

        if self._store_cm is not None:
            await self._store_cm.__aexit__(None, None, None)
            self._store_cm = None
            self._store = None
        
        print("✅ Database connections closed")
    
    async def get_checkpointer(self) -> AsyncPostgresSaver:
        """Return a live AsyncPostgresSaver.

        We enter the async context manager once and cache the saver so that
        subsequent calls reuse the same database connection pool.  LangGraph
        expects the *real* saver object (it calls methods like
        ``get_next_version``), so returning the context manager wrapper would
        fail.
        """
        if not hasattr(self, '_langgraph_dsn'):
            raise RuntimeError("Database not initialized")
        if self._checkpointer is None:
            self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(self._langgraph_dsn)
            self._checkpointer = await self._checkpointer_cm.__aenter__()
            # Ensure required tables exist (idempotent)
            await self._checkpointer.setup()
        return self._checkpointer
    
    async def get_store(self) -> AsyncPostgresStore:
        """Return a live AsyncPostgresStore instance (vector + KV)."""
        if not hasattr(self, '_langgraph_dsn'):
            raise RuntimeError("Database not initialized")
        if self._store is None:
            self._store_cm = AsyncPostgresStore.from_conn_string(self._langgraph_dsn)
            self._store = await self._store_cm.__aenter__()
            # ensure schema
            await self._store.setup()
        return self._store
    
    def get_engine(self) -> AsyncEngine:
        """Get the SQLAlchemy engine for metadata tables"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        return self.engine


# Global database manager instance
db_manager = DatabaseManager()
