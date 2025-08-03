from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, AsyncIterator, Callable
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


# -----------------------------
# Dummy user and middleware
# -----------------------------
class DummyUser:
    def __init__(self, identity: str = "test-user", display_name: str = "Test User"):
        self.identity = identity
        self.display_name = display_name
        self.is_authenticated = True

    def to_dict(self) -> Dict[str, Any]:
        return {"identity": self.identity, "display_name": self.display_name}


def install_dummy_user_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def inject_dummy_user(request, call_next):
        request.scope["user"] = DummyUser()
        return await call_next(request)


# -----------------------------
# Dummy/override Async DB session
# -----------------------------
class DummySessionBase:
    """
    Minimal emulation of SQLAlchemy AsyncSession used by the app code.

    Override scalar/scalars/commit/refresh in subclasses/fixtures to return
    appropriate rows for a test. By default, returns empty data.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    # AsyncSession.add is sync in SQLAlchemy; keep it sync here
    def add(self, _):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def scalar(self, _stmt):
        return None

    async def scalars(self, _stmt):
        class Result:
            def all(self_inner):
                return []
        return Result()


def override_get_session_dep(session_factory: Callable[[], DummySessionBase]) -> Callable[[], AsyncIterator[DummySessionBase]]:
    async def _dep():
        yield session_factory()
    return _dep


# -----------------------------
# LangGraph fakes
# -----------------------------
class FakeSnapshot:
    def __init__(self, values: Dict[str, Any], cfg: Dict[str, Any], created_at=None, next_nodes: Optional[List[str]] = None):
        self.values = values
        self.metadata = {}
        self.config = cfg
        self.parent_config = {}
        self.created_at = created_at
        self.next = next_nodes or []


def make_snapshot(values: Dict[str, Any], cfg: Dict[str, Any], created_at=None, next_nodes: Optional[List[str]] = None) -> FakeSnapshot:
    return FakeSnapshot(values, cfg, created_at, next_nodes)


class FakeAgent:
    def __init__(self, snapshots: List[FakeSnapshot]):
        self._snapshots = snapshots

    async def aget_state_history(self, config, **_kwargs):
        # Yield snapshots as provided
        for s in self._snapshots:
            yield s


class FakeGraph:
    def __init__(self, events: List[Any]):
        self._events = events

    async def astream(self, _input, config=None, stream_mode=None):
        for e in self._events:
            yield e


# -----------------------------
# Patching helpers
# -----------------------------
class MockLangGraphService:
    def __init__(self, agent: Optional[FakeAgent] = None, graph: Optional[FakeGraph] = None):
        self._agent = agent
        self._graph = graph

    async def get_graph(self, _graph_id: str):
        if self._agent is not None:
            return self._agent
        if self._graph is not None:
            return self._graph
        raise RuntimeError("No fake agent/graph configured")


def patch_langgraph_service(agent: Optional[FakeAgent] = None, graph: Optional[FakeGraph] = None):
    """
    Context manager yielding a patched get_langgraph_service that returns the fake.
    Usage:
        with patch_langgraph_service(agent=fake_agent):
            ... tests ...
    """
    fake = MockLangGraphService(agent=agent, graph=graph)
    return patch("agent_server.services.langgraph_service.get_langgraph_service", autospec=True, return_value=fake)


# -----------------------------
# App factory for tests
# -----------------------------
def create_test_app(include_runs: bool = True, include_threads: bool = True) -> FastAPI:
    """
    Build a FastAPI app with our routers mounted and dummy user middleware installed.
    Dependency overrides must be installed by the caller to control DB behavior.
    """
    app = FastAPI()
    install_dummy_user_middleware(app)

    if include_threads:
        from agent_server.api import threads as threads_module
        app.include_router(threads_module.router)

    if include_runs:
        from agent_server.api import runs as runs_module
        app.include_router(runs_module.router)

    return app


def make_client(app: FastAPI) -> TestClient:
    return TestClient(app)
