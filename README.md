# Agent Protocol Server

> **Replace LangGraph Platform with your own backend – zero vendor lock-in, full control.**

An open-source, production-ready backend for running, persisting, and streaming AI agents with LangGraph compatibility. Built with FastAPI and PostgreSQL for developers who demand control over their agent orchestration.

Based on the [Agent Protocol specification](https://github.com/langchain-ai/agent-protocol), with modifications to maintain backward compatibility with the LangGraph Client SDK.

**Status**: Work in progress — actively improving DX, protocol coverage, and production hardening. Contributors welcome!

## ✨ Why This Exists

- **Zero Vendor Lock-in**: Own your agent infrastructure completely
- **Drop-in Replacement**: Backward compatible with LangGraph Client SDK
- **Production Ready**: PostgreSQL persistence, streaming, auth
- **Developer First**: Clean OSS implementation that's easy to run and evolve

## 🚀 Quick Start (5 minutes)

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- uv (Python package manager)
- Docker (for local Postgres)

### Get Running

```bash
# Clone and setup
git clone <repository-url>
cd langgraph-agent-server
uv install

# Start database
docker-compose up -d postgres

# Launch server
uv run uvicorn src.agent_server.main:app --reload
```

### Verify It Works

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs  # Interactive API docs
```

## 🏗️ Architecture

```
Client → FastAPI → LangGraph SDK → PostgreSQL
         ↓           ↓              ↓
   Agent Protocol  Auth/Graph   Checkpoints
   Endpoints       Execution     Metadata
```

- **FastAPI**: HTTP layer with Agent Protocol compliance
- **LangGraph**: State management and graph execution
- **PostgreSQL**: Durable state and metadata storage
- **Config-driven**: `langgraph.json` maps graphs to endpoints

## 📁 Project Structure

```
langgraph-agent-server/
├── langgraph.json              # Graph configuration
├── auth.py                     # Authentication setup
├── graphs/                     # Agent definitions
│   └── weather_agent.py        # Example agent
├── src/agent_server/           # FastAPI application
│   ├── main.py                 # App entrypoint
│   ├── core/                   # Database & infrastructure
│   ├── models/                 # Pydantic schemas
│   ├── services/               # Business logic
│   └── utils/                  # Helpers
└── tests/                      # Test suite
```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/langgraph_agent_server

# Authentication
AUTH_TYPE=noop  # noop, jwt, oauth, custom

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# LLM API Key (if using chat_agent.py)
OPENAI_API_KEY=sk-...
```

### Graph Configuration (langgraph.json)

```json
{
  "graphs": {
    "weather_agent": "./graphs/weather_agent.py:graph"
  },
  "auth": {
    "path": "./auth.py:auth"
  }
}
```

## 🧪 Try the Example Agent

```bash
# Create a thread
curl -X POST http://localhost:8000/threads \
  -H "Content-Type: application/json" \
  -d '{}'

# Start a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "weather_agent",
    "thread_id": "<YOUR_THREAD_ID>",
    "input": {"location": "San Francisco"}
  }'
```

## 🎯 What You Get

- ✅ **Agent Protocol-compliant REST endpoints**
- ✅ **Persistent conversations with database-backed checkpoints**
- ✅ **Config-driven agent graphs**
- ✅ **Pluggable authentication (JWT, OAuth, custom)**
- ✅ **Streaming responses with network drop resilience**
- ✅ **Backward compatible with LangGraph Client SDK** (uses "assistant" naming in schemas for compatibility)
- ✅ **Production-ready with Docker, monitoring, CI/CD**

## 📊 Development Status

### ✅ Phase 1: Foundation (Complete)

- Project structure and dependencies
- FastAPI application with LangGraph integration
- Database setup with PostgreSQL
- Basic authentication framework
- Health checks and development environment

### 🔄 Phase 2: Agent Protocol API (In Progress)

- Assistant management endpoints
- Thread creation and management
- Run execution with streaming
- Store operations (key-value + vector)

### 📋 Phase 3: Production Features (Planned)

- Comprehensive authentication backends
- Multi-tenant isolation
- Monitoring and metrics
- Deployment configurations

## 🛣️ Roadmap

- **Human-in-the-loop interrupts** (pause/resume, manual decisions)
- **Redis-backed streaming buffers** for resilience and scale
- **Langfuse integration** for tracing
- **Assistant management endpoints** and improved UX
- **Store operations** (kv + vector)
- **Multi-tenant isolation** and auth backends
- **Deployment recipes** (Docker/K8s)

## 🚀 Production Deployment

- Run with multiple workers behind a reverse proxy
- Use managed PostgreSQL with backups and monitoring
- Configure proper auth (JWT/OIDC) and CORS
- Export metrics/logs to your observability stack

## 🤝 Contributing

We're looking for contributors to:

- Improve spec alignment and API ergonomics
- Harden streaming/resume semantics
- Add auth backends and deployment guides
- Expand examples and tests

**Open issues/PRs** - run tests and follow style guidelines.

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.
