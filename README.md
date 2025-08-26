# Aegra - Open Source LangGraph Platform Alternative

<p align="center">
  <strong>Self-hosted AI agent backend. LangGraph power without vendor lock-in.</strong>
</p>

<p align="center">
  <a href="https://github.com/ibbybuilds/aegra/stargazers"><img src="https://img.shields.io/github/stars/ibbybuilds/aegra" alt="GitHub stars"></a>
  <a href="https://github.com/ibbybuilds/aegra/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ibbybuilds/aegra" alt="License"></a>
  <a href="https://github.com/ibbybuilds/aegra/issues"><img src="https://img.shields.io/github/issues/ibbybuilds/aegra" alt="Issues"></a>
</p>

Replace LangGraph Platform with your own infrastructure. Built with FastAPI + PostgreSQL for developers who demand complete control over their agent orchestration.

**🔌 Agent Protocol Compliant**: Aegra implements the [Agent Protocol](https://github.com/langchain-ai/agent-protocol) specification, an open-source standard for serving LLM agents in production.

**🎯 Perfect for:** Teams escaping vendor lock-in • Data sovereignty requirements • Custom deployments • Cost optimization

---

## 🔥 Why Aegra vs LangGraph Platform?

| Feature                | LangGraph Platform         | Aegra (Self-Hosted)                               |
| ---------------------- | -------------------------- | ------------------------------------------------- |
| **Cost**               | $$$+ per month             | **Free** (self-hosted), infra-cost only           |
| **Data Control**       | Third-party hosted         | **Your infrastructure**                           |
| **Vendor Lock-in**     | High dependency            | **Zero lock-in**                                  |
| **Customization**      | Platform limitations       | **Full control**                                  |
| **API Compatibility**  | LangGraph SDK              | **Same LangGraph SDK**                            |
| **Authentication**     | Lite: no custom auth       | **Custom auth** (JWT/OAuth/Firebase/NoAuth)       |
| **Database Ownership** | No bring-your-own database | **BYO Postgres** (you own credentials and schema) |
| **Tracing/Telemetry**  | Forced LangSmith in SaaS   | **Your choice** (Langfuse/None)                   |

## ✨ Core Benefits

- **🏠 Self-Hosted**: Run on your infrastructure, your rules
- **🔄 Drop-in Replacement**: Use existing LangGraph Client SDK without changes
- **🛡️ Production Ready**: PostgreSQL persistence, streaming, authentication
- **📊 Zero Vendor Lock-in**: Apache 2.0 license, open source, full control
- **🚀 Fast Setup**: 5-minute deployment with Docker
- **🔌 Agent Protocol Compliant**: Implements the open-source [Agent Protocol](https://github.com/langchain-ai/agent-protocol) specification
- **💬 Agent Chat UI Compatible**: Works seamlessly with [LangChain's Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)

## 🚀 Quick Start (5 minutes)

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- uv (Python package manager)

### Get Running

```bash
# Clone and setup
git clone https://github.com/ibbybuilds/aegra.git
cd aegra
# Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync env and dependencies
uv sync

# Activate environment
source .venv/bin/activate  # Mac/Linux
# OR .venv/Scripts/activate  # Windows

# Environment
cp .env.example .env

# Start everything (database + migrations + server)
docker compose up aegra
```

### Verify It Works

```bash
# Health check
curl http://localhost:8000/health

# Interactive API docs
open http://localhost:8000/docs
```

You now have a self-hosted LangGraph Platform alternative running locally.

## 💬 Agent Chat UI Compatible

Aegra works seamlessly with [LangChain's Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Simply set `NEXT_PUBLIC_API_URL=http://localhost:8000` and `NEXT_PUBLIC_ASSISTANT_ID=agent` in your Agent Chat UI environment to connect to your Aegra backend.

## 👨‍💻 For Developers

**New to database migrations?** Check out our guides:

- **📚 [Developer Guide](docs/developer-guide.md)** - Complete setup, migrations, and development workflow
- **⚡ [Migration Cheatsheet](docs/migration-cheatsheet.md)** - Quick reference for common commands

**Quick Development Commands:**

```bash
# Docker development (recommended)
docker compose up aegra

# Local development
docker compose up postgres -d
python3 scripts/migrate.py upgrade
python3 run_server.py

# Create new migration
python3 scripts/migrate.py revision --autogenerate -m "Add new feature"
```

## 🧪 Try the Example Agent

Use the **same LangGraph Client SDK** you're already familiar with:

```python
import asyncio
from langgraph_sdk import get_client

async def main():
    # Connect to your self-hosted Aegra instance
    client = get_client(url="http://localhost:8000")

    # Create assistant (same API as LangGraph Platform)
    assistant = await client.assistants.create(
        graph_id="agent",
        if_exists="do_nothing",
        config={},
    )
    assistant_id = assistant["assistant_id"]

    # Create thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # Stream responses (identical to LangGraph Platform)
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {"type": "human", "content": [{"type": "text", "text": "hello"}]}
            ]
        },
        stream_mode=["values", "messages-tuple", "custom"],
        on_disconnect="cancel",
    )

    async for chunk in stream:
        print(f"event: {getattr(chunk, 'event', None)}, data: {getattr(chunk, 'data', None)}")

asyncio.run(main())
```

**Key Point**: Your existing LangGraph applications work without modification! 🔄

## 🏗️ Architecture

```text
Client → FastAPI → LangGraph SDK → PostgreSQL
 ↓         ↓           ↓             ↓
Agent    HTTP     State        Persistent
SDK      API    Management      Storage
```

### Components

- **FastAPI**: Agent Protocol-compliant HTTP layer
- **LangGraph**: State management and graph execution
- **PostgreSQL**: Durable checkpoints and metadata
- **Agent Protocol**: Open-source specification for LLM agent APIs
- **Config-driven**: `aegra.json` for graph definitions


## 📁 Project Structure

```text
aegra/
├── aegra.json           # Graph configuration
├── auth.py              # Authentication setup
├── graphs/              # Agent definitions
│   └── react_agent/     # Example ReAct agent
├── src/agent_server/    # FastAPI application
│   ├── main.py         # Application entrypoint
│   ├── core/           # Database & infrastructure
│   ├── models/         # Pydantic schemas
│   ├── services/       # Business logic
│   └── utils/          # Helper functions
├── tests/              # Test suite
└── deployments/        # Docker & K8s configs
```

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure values:

```bash
cp .env.example .env
```

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/aegra

# Authentication (extensible)
AUTH_TYPE=noop  # noop, custom

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# LLM Providers
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
# TOGETHER_API_KEY=...
```

### Graph Configuration

`aegra.json` defines your agent graphs:

```json
{
  "graphs": {
    "agent": "./graphs/react_agent/graph.py:graph"
  }
}
```

## 🎯 What You Get

### ✅ **Core Features**

- [Agent Protocol](https://github.com/langchain-ai/agent-protocol)-compliant REST endpoints
- Persistent conversations with PostgreSQL checkpoints
- Streaming responses with network resilience
- Config-driven agent graph management
- Compatible with LangGraph Client SDK

### ✅ **Production Ready**

- Docker containerization
- Database migrations with Alembic
- Comprehensive test suite
- Authentication framework (JWT/OAuth ready)
- Health checks and monitoring endpoints

### ✅ **Developer Experience**

- Interactive API documentation (FastAPI)
- Hot reload in development
- Clear error messages and logging
- Extensible architecture
- **📚 [Developer Guide](docs/developer-guide.md)** - Complete setup, migrations, and development workflow
- **⚡ [Migration Cheatsheet](docs/migration-cheatsheet.md)** - Quick reference for common commands

## 🛣️ Roadmap

**✅ Completed**

- Agent Chat UI compatibility
- Agent Protocol API implementation
- PostgreSQL persistence and streaming
- Authentication framework

**🎯 Next**

- Human-in-the-loop interrupts
- Redis-backed streaming buffers
- Langfuse integration
- Advanced deployment recipes

**🚀 Future**

- Multi-tenant architecture
- Performance optimizations
- Additional LLM provider integrations
- Custom UI themes and branding

## 🤝 Contributing

We welcome contributions! Here's how you can help:

**🐛 Issues & Bugs**

- Report bugs with detailed reproduction steps
- Suggest new features and improvements
- Help with documentation

**💻 Code Contributions**

- Improve Agent Protocol spec alignment
- Add authentication backends
- Enhance testing coverage
- Optimize performance

**📚 Documentation**

- Deployment guides
- Integration examples
- Best practices

**Get Started**: Check out [CONTRIBUTING.md](CONTRIBUTING.md), our [Developer Guide](docs/developer-guide.md), and our [good first issues](https://github.com/ibbybuilds/aegra/labels/good%20first%20issue).

## 📄 License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.

---

<p align=\"center\">
  <strong>⭐ If Aegra helps you escape vendor lock-in, please star the repo! ⭐</strong><br>
  <sub>Built with ❤️ by developers who believe in infrastructure freedom</sub>
</p>
