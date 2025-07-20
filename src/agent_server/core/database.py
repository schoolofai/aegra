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
        self.checkpointer: Optional[AsyncPostgresSaver] = None
        self.store: Optional[AsyncPostgresStore] = None
        self._database_url = os.getenv(
            "DATABASE_URL", 
            "postgresql+asyncpg://user:password@localhost:5432/langgraph_agent_server"
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
        
        # Initialize official LangGraph checkpointer
        self.checkpointer = AsyncPostgresSaver.from_conn_string(dsn)
        # Note: LangGraph components auto-create tables on first use
        
        # Initialize official LangGraph store
        self.store = AsyncPostgresStore.from_conn_string(dsn)
        # Note: LangGraph components auto-create tables on first use
        
        # Create our minimal metadata tables
        await self._create_metadata_tables()
        
        print("✅ Database and LangGraph components initialized")
    
    async def _create_metadata_tables(self):
        """Create Agent Protocol metadata tables"""
        async with self.engine.begin() as conn:
            # Create tables one by one (asyncpg doesn't support multiple statements)
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assistants (
                    assistant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
                    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id TEXT NOT NULL,
                    assistant_id UUID REFERENCES assistants(assistant_id),
                    status TEXT DEFAULT 'pending',
                    input JSONB,
                    output JSONB,
                    error TEXT,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                )
            """))
            
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS thread_metadata (
                    thread_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'idle',
                    metadata JSONB DEFAULT '{}',
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            
            # Create indexes
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_assistants_user ON assistants(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_thread_user ON thread_metadata(user_id)"))
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        
        # LangGraph components handle their own connection cleanup
        
        print("✅ Database connections closed")
    
    def get_checkpointer(self) -> AsyncPostgresSaver:
        """Get the LangGraph checkpointer instance"""
        if not self.checkpointer:
            raise RuntimeError("Database not initialized")
        return self.checkpointer
    
    def get_store(self) -> AsyncPostgresStore:
        """Get the LangGraph store instance"""
        if not self.store:
            raise RuntimeError("Database not initialized") 
        return self.store
    
    def get_engine(self) -> AsyncEngine:
        """Get the SQLAlchemy engine for metadata tables"""
        if not self.engine:
            raise RuntimeError("Database not initialized")
        return self.engine


# Global database manager instance
db_manager = DatabaseManager()