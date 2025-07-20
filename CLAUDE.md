# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install dependencies
uv install

# Activate virtual environment (if needed)
source .venv/bin/activate
```

### Running the Application
```bash
# Start development server with auto-reload
uv run uvicorn src.agent_server.main:app --reload

# Start with specific host/port
uv run uvicorn src.agent_server.main:app --host 0.0.0.0 --port 8000 --reload

# Start development database
docker-compose up -d postgres
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api/test_assistants.py

# Run tests with async support
uv run pytest -v --asyncio-mode=auto

# Health check endpoint test
curl http://localhost:8000/health
```

### Database Management
```bash
# Database migrations (when implemented)
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## High-Level Architecture

This is an **Agent Protocol server** that acts as an HTTP wrapper around **official LangGraph packages**. The key architectural principle is that LangGraph handles ALL state persistence and graph execution, while the FastAPI layer only provides Agent Protocol compliance.

### Core Integration Pattern

**Database Architecture**: The system uses a hybrid approach:
- **LangGraph manages state**: Official `AsyncPostgresSaver` and `AsyncPostgresStore` handle conversation checkpoints, state history, and long-term memory
- **Minimal metadata tables**: Our SQLAlchemy models only track Agent Protocol metadata (assistants, runs, thread_metadata)
- **URL format difference**: LangGraph requires `postgresql://` while our SQLAlchemy uses `postgresql+asyncpg://`

### Configuration System

**langgraph.json**: Central configuration file that defines:
- Graph definitions: `"weather_agent": "./graphs/weather_agent.py:graph"`
- Authentication: `"auth": {"path": "./auth.py:auth"}`
- Dependencies and environment

**auth.py**: Uses LangGraph SDK Auth patterns:
- `@auth.authenticate` decorator for user authentication
- `@auth.on.{resource}.{action}` for resource-level authorization
- Returns `Auth.types.MinimalUserDict` with user identity and metadata

### Database Manager Pattern

**DatabaseManager** (src/agent_server/core/database.py):
- Initializes both SQLAlchemy engine and LangGraph components
- Handles URL conversion between asyncpg and psycopg formats
- Provides singleton access to checkpointer and store instances
- Auto-creates LangGraph tables via `.setup()` calls

### Graph Loading Strategy

Agents are Python modules that export a compiled `graph` variable:
```python
# graphs/weather_agent.py
workflow = StateGraph(WeatherState)
# ... define nodes and edges
graph = workflow.compile()  # Must export as 'graph'
```

### FastAPI Integration

**Lifespan Management**: The app uses `@asynccontextmanager` to properly initialize/cleanup LangGraph components during FastAPI startup/shutdown.

**Health Checks**: Comprehensive health endpoint tests connectivity to:
- SQLAlchemy database engine
- LangGraph checkpointer 
- LangGraph store

### Authentication Flow

1. HTTP request with Authorization header
2. LangGraph SDK Auth extracts and validates token
3. Returns user context with identity, permissions, org_id
4. Resource handlers filter data based on user context
5. Multi-tenant isolation via user metadata injection

## Key Dependencies

- **langgraph**: Core graph execution framework
- **langgraph-checkpoint-postgres**: Official PostgreSQL state persistence  
- **langgraph-sdk**: Authentication and SDK components
- **psycopg[binary]**: Required by LangGraph packages (not asyncpg)
- **FastAPI + uvicorn**: HTTP API layer
- **SQLAlchemy**: For Agent Protocol metadata tables only

## Development Patterns

**Import patterns**: Always use relative imports within the package and absolute imports for external dependencies.

**Database access**: Use `db_manager.get_checkpointer()` and `db_manager.get_store()` for LangGraph operations, `db_manager.get_engine()` for metadata queries.

**Error handling**: Use `Auth.exceptions.HTTPException` for authentication errors to maintain LangGraph SDK compatibility.

**Testing**: Tests should be async-aware and use pytest-asyncio for proper async test support.

Always run lint and typecheck commands (`npm run lint`, `npm run typecheck`, `ruff`, etc.) before completing tasks if they are available in the project.