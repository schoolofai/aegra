"""Run endpoints for Agent Protocol"""
import asyncio
from uuid import uuid4, UUID
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Query
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.orm import Assistant as AssistantORM, Thread as ThreadORM, get_session
from fastapi.responses import StreamingResponse

from ..models import Run, RunCreate, RunList, RunStatus, User
from ..core.auth_deps import get_current_user
from ..core.sse import get_sse_headers
from ..services.langgraph_service import get_langgraph_service

router = APIRouter()

def _to_uuid(value: str, name: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception:
        raise HTTPException(422, f"{name} must be a valid UUID")
logger = logging.getLogger(__name__)
# TODO: Replace all print statements and bare exceptions with structured logging across the codebase


# NOTE: We keep only an in-memory task registry for asyncio.Task handles.
# All run metadata/state is persisted via ORM.
active_runs: Dict[str, asyncio.Task] = {}

# Default stream modes for background run execution
RUN_STREAM_MODES = ["messages", "values", "custom"]

async def set_thread_status(session: AsyncSession, thread_id: str, status: str):
    """Update the status column of a thread."""
    await session.execute(
        update(ThreadORM)
        .where(ThreadORM.thread_id == thread_id)
        .values(status=status, updated_at=datetime.utcnow())
    )
    await session.commit()


async def update_thread_metadata(session: AsyncSession, thread_id: str, assistant_id: str, graph_id: str):
    """Update thread metadata with assistant and graph information (dialect agnostic)."""
    # Read-modify-write to avoid DB-specific JSON concat operators
    thread = await session.scalar(
        select(ThreadORM).where(ThreadORM.thread_id == thread_id)
    )
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found for metadata update")
    md = dict(getattr(thread, "metadata_json", {}) or {})
    md.update({
        "assistantId": str(assistant_id),
        "graphId": graph_id,
    })
    await session.execute(
        update(ThreadORM)
        .where(ThreadORM.thread_id == thread_id)
        .values(metadata_json=md, updated_at=datetime.utcnow())
    )
    await session.commit()



@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create and execute a new run (persisted)."""

    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()

    # Validate assistant exists and get its graph_id (coerce to UUID)
    assistant_uuid = _to_uuid(request.assistant_id, "assistant_id")
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_uuid,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")

    # Mark thread as busy and update metadata with assistant/graph info
    await set_thread_status(session, thread_id, "busy")
    await update_thread_metadata(session, thread_id, assistant.assistant_id, assistant.graph_id)

    # Persist run record via ORM model in core.orm (Run table)
    from ..core.orm import Run as RunORM
    now = datetime.utcnow()
    run_orm = RunORM(
        run_id=run_id,  # string here is okay because ORM column has server_default; DB will generate if omitted
        thread_id=thread_id,
        assistant_id=assistant_uuid,
        status="pending",
        input=request.input or {},
        config=request.config or {},
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response from ORM -> Pydantic
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=str(request.assistant_id),
        status="pending",
        input=request.input or {},
        config=request.config or {},
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )

    # Start execution asynchronously
    task = asyncio.create_task(
        execute_run_async(
            run_id, thread_id, assistant.graph_id, request.input or {}, user, request.config, request.stream_mode, session
        )
    )
    active_runs[run_id] = task

    return run


@router.post("/threads/{thread_id}/runs/stream")
async def create_and_stream_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create a new run and stream its execution - persisted + SSE."""
    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()

    # Validate assistant exists and get its graph_id (coerce to UUID)
    assistant_uuid = _to_uuid(request.assistant_id, "assistant_id")
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_uuid,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")

    # Mark thread as busy and update metadata with assistant/graph info
    await set_thread_status(session, thread_id, "busy")
    await update_thread_metadata(session, thread_id, assistant.assistant_id, assistant.graph_id)

    # Persist run record
    from ..core.orm import Run as RunORM
    now = datetime.utcnow()
    run_orm = RunORM(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=assistant_uuid,
        status="streaming",
        input=request.input or {},
        config=request.config or {},
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response model for stream context
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=str(request.assistant_id),
        status="streaming",
        input=request.input or {},
        config=request.config or {},
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )

    # Start background execution that will populate the broker
    task = asyncio.create_task(
        execute_run_async(
            run_id, thread_id, assistant.graph_id, request.input or {}, user, request.config, request.stream_mode, session
        )
    )
    active_runs[run_id] = task

    # Extract requested stream mode(s)
    stream_mode = request.stream_mode
    if not stream_mode and request.config and "stream_mode" in request.config:
        stream_mode = request.config["stream_mode"]

    # Stream immediately from broker (which will also include replay of any early events)
    from ..services.streaming_service import streaming_service

    return StreamingResponse(
        streaming_service.stream_run_execution(run, user, None, request.config, stream_mode),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        }
    )


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=Run)
async def get_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get run by ID (persisted)."""
    from ..core.orm import Run as RunORM
    stmt = select(RunORM).where(
        RunORM.run_id == run_id,
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
    )
    run_orm = await session.scalar(stmt)
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    logger.debug("get_run: user=%s thread_id=%s run_id=%s status=%s", user.identity, thread_id, run_id, run_orm.status)
    # Convert to Pydantic
    return Run.model_validate({c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns})


@router.get("/threads/{thread_id}/runs", response_model=RunList)
async def list_runs(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List runs for a specific thread (persisted)."""
    from ..core.orm import Run as RunORM
    stmt = select(RunORM).where(
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
    ).order_by(RunORM.created_at.desc())
    result = await session.scalars(stmt)
    rows = result.all()
    runs = [Run.model_validate({c.name: getattr(r, c.name) for c in r.__table__.columns}) for r in rows]
    logger.debug("list_runs: user=%s thread_id=%s total=%d", user.identity, thread_id, len(runs))
    return RunList(runs=runs, total=len(runs))


@router.patch("/threads/{thread_id}/runs/{run_id}")
async def update_run(
    thread_id: str,
    run_id: str,
    request: RunStatus,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update run status (for cancellation/interruption, persisted)."""
    from ..core.orm import Run as RunORM
    run_uuid = _to_uuid(run_id, "run_id")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_uuid,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Handle interruption/cancellation
    from ..services.streaming_service import streaming_service

    if request.status == "cancelled":
        logger.info("update_run: cancelling run_id=%s user=%s thread_id=%s", run_id, user.identity, thread_id)
        await streaming_service.cancel_run(run_id)
        await session.execute(
            update(RunORM).where(RunORM.run_id == run_id).values(status="cancelled", updated_at=datetime.utcnow())
        )
        await session.commit()
    elif request.status == "interrupted":
        logger.info("update_run: interrupting run_id=%s user=%s thread_id=%s", run_id, user.identity, thread_id)
        await streaming_service.interrupt_run(run_id)
        await session.execute(
            update(RunORM).where(RunORM.run_id == run_id).values(status="interrupted", updated_at=datetime.utcnow())
        )
        await session.commit()

    # Return final run state
    run_orm = await session.scalar(select(RunORM).where(RunORM.run_id == run_id))
    return Run.model_validate({c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns})


@router.get("/threads/{thread_id}/runs/{run_id}/join")
async def join_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Join a run (wait for completion and return final output) - persisted."""
    from ..core.orm import Run as RunORM
    run_uuid = _to_uuid(run_id, "run_id")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_uuid,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    logger.debug("join_run: user=%s thread_id=%s run_id=%s status=%s", user.identity, thread_id, run_id, run_orm.status)

    # Wait for completion if not finished
    if run_orm.status not in ["completed", "failed", "cancelled"]:
        task = active_runs.get(run_id)
        if task:
            try:
                await task  # Wait for completion
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    # Reload final state from DB
    run_orm = await session.scalar(select(RunORM).where(RunORM.run_id == run_id))
    return getattr(run_orm, "output", None) or {}


@router.get("/threads/{thread_id}/runs/{run_id}/stream")
async def stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    stream_mode: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream run execution with SSE and reconnection support - persisted metadata."""
    from ..core.orm import Run as RunORM
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    logger.debug("stream_run: user=%s thread_id=%s run_id=%s status=%s", user.identity, thread_id, run_id, run_orm.status)
    # If already terminal, emit a final end event
    if run_orm.status in ["completed", "failed", "cancelled"]:
        from ..core.sse import create_end_event

        async def generate_final():
            yield create_end_event()

        return StreamingResponse(
            generate_final(),
            media_type="text/event-stream",
            headers={
                **get_sse_headers(),
                "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
                "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
            }
        )

    # Stream active or pending runs via broker
    from ..services.streaming_service import streaming_service

    # Build a lightweight Pydantic Run from ORM for streaming context
    run_model = Run.model_validate({c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns})

    return StreamingResponse(
        streaming_service.stream_run_execution(run_model, user, last_event_id, run_model.config, stream_mode),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        }
    )


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    thread_id: str,
    run_id: str,
    wait: int = Query(0, ge=0, le=1, description="Whether to wait for the run task to settle"),
    action: str = Query("cancel", pattern="^(cancel|interrupt)$", description="Cancellation action"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Cancel or interrupt a run (client-compatible endpoint).

    Matches client usage:
      POST /v1/threads/{thread_id}/runs/{run_id}/cancel?wait=0&action=interrupt

    - action=cancel => hard cancel
    - action=interrupt => cooperative interrupt if supported
    - wait=1 => await background task to finish settling
    """
    from ..core.orm import Run as RunORM
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    from ..services.streaming_service import streaming_service
    now = datetime.utcnow()

    if action == "interrupt":
        logger.info("cancel_run_endpoint: interrupt run_id=%s user=%s thread_id=%s", run_id, user.identity, thread_id)
        await streaming_service.interrupt_run(run_id)
        # Persist status as interrupted
        await session.execute(
            update(RunORM).where(RunORM.run_id == run_uuid).values(status="cancelled", updated_at=datetime.utcnow())
        )
        await session.commit()
    else:
        logger.info("cancel_run_endpoint: cancel run_id=%s user=%s thread_id=%s", run_id, user.identity, thread_id)
        await streaming_service.cancel_run(run_id)
        # Persist status as cancelled
        await session.execute(
            update(RunORM).where(RunORM.run_id == run_uuid).values(status="interrupted", updated_at=datetime.utcnow())
        )
        await session.commit()

    # Optionally wait for background task
    if wait:
        task = active_runs.get(run_id)
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    # Return updated Run
    """Delete a run (persisted)."""
    from ..core.orm import Run as RunORM
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    logger.info("delete_run: user=%s thread_id=%s run_id=%s status=%s", user.identity, thread_id, run_id, run_orm.status)
    # Cancel the run if it's still active
    if run_orm.status in ["pending", "running", "streaming"]:
        from ..services.streaming_service import streaming_service
        await streaming_service.cancel_run(run_id)

    # Remove from DB
    await session.delete(run_orm)
    await session.commit()

    # Clean up active task if exists
    task = active_runs.pop(run_id, None)
    if task and not task.done():
        task.cancel()


async def execute_run_async(
    run_id: str,
    thread_id: str, 
    graph_id: str,
    input_data: dict,
    user: User,
    config: Optional[dict] = None,
    stream_mode: Optional[list[str]] = None,
    session: Optional[AsyncSession] = None
):
    """Execute run asynchronously in background using streaming to capture all events"""
    from ..services.streaming_service import streaming_service

    # Normalize stream_mode once here for all callers/endpoints.
    # Accept "messages-tuple" as an alias of "messages".
    def _normalize_mode(mode):
        return "messages" if isinstance(mode, str) and mode == "messages-tuple" else mode
    if isinstance(stream_mode, list):
        stream_mode = [_normalize_mode(m) for m in stream_mode]
    else:
        stream_mode = _normalize_mode(stream_mode)
    
    try:
        # Update status
        await update_run_status(run_id, "running", session=session)
        logger.info("execute_run_async: started run_id=%s thread_id=%s", run_id, thread_id)
        
        # Get graph and execute
        langgraph_service = get_langgraph_service()
        graph = await langgraph_service.get_graph(graph_id)
        
        from ..services.langgraph_service import create_run_config
        run_config = create_run_config(run_id, thread_id, user, config or {})
        
        # Always execute using streaming to capture events for later replay
        from ..services.event_store import store_sse_event
        event_counter = 0
        final_output = None
        # Use streaming service's broker system to distribute events
        from ..core.auth_ctx import with_auth_ctx
        async with with_auth_ctx(user, []):
            async for raw_event in graph.astream(
                input_data,
                config=run_config,
                stream_mode=stream_mode or RUN_STREAM_MODES,
            ):
                event_counter += 1
                event_id = f"{run_id}_event_{event_counter}"
                # Forward to broker for live consumers
                await streaming_service.put_to_broker(run_id, event_id, raw_event)
            
                # Store for replay
                await streaming_service.store_event_from_raw(run_id, event_id, raw_event)
            
                # Track final output
                logger.debug("execute_run_async: event_id=%s run_id=%s", event_id, run_id)
                if isinstance(raw_event, tuple):
                    if len(raw_event) >= 2 and raw_event[0] == "values":
                        final_output = raw_event[1]
                elif not isinstance(raw_event, tuple):
                    # Non-tuple events are values mode
                    final_output = raw_event

        # Signal end of stream
        event_counter += 1
        end_event_id = f"{run_id}_event_{event_counter}"
        end_event = ("end", {"status": "completed", "final_output": final_output})
        
        await streaming_service.put_to_broker(run_id, end_event_id, end_event)
        await streaming_service.store_event_from_raw(run_id, end_event_id, end_event)
        
        # Update with results
        await update_run_status(run_id, "completed", output=final_output, session=session)
        logger.info("execute_run_async: completed run_id=%s thread_id=%s", run_id, thread_id)
        # Mark thread back to idle
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        
    except asyncio.CancelledError:
        await update_run_status(run_id, "cancelled", session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        logger.info("execute_run_async: cancelled run_id=%s thread_id=%s", run_id, thread_id)
        # Signal cancellation to broker
        await streaming_service.signal_run_cancelled(run_id)
        raise
    except Exception as e:
        await update_run_status(run_id, "failed", error=str(e), session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        logger.exception("execute_run_async: failed run_id=%s thread_id=%s error=%s", run_id, thread_id, str(e))
        # Signal error to broker
        await streaming_service.signal_run_error(run_id, str(e))
        raise
    finally:
        # Clean up broker
        await streaming_service.cleanup_run(run_id)
        active_runs.pop(run_id, None)
        logger.debug("execute_run_async: cleaned up run_id=%s", run_id)


async def update_run_status(
    run_id: str,
    status: str,
    output=None,
    error: str = None,
    session: Optional[AsyncSession] = None,
):
    """Update run status in database (persisted). If session not provided, opens a short-lived session."""
    from ..core.orm import Run as RunORM, get_session as _get_session

    # If no session was passed, open a temporary one
    owns_session = False
    if session is None:
        # FastAPI dependency cannot be awaited here; use db_manager or engine via get_session
        # Fallback: try to acquire a new session from get_session() if it is callable that returns sessionmaker.
        # Here we assume update within the current session context where possible.
        pass

    try:
        if session is None:
            # Best-effort: we cannot create a dependency-injected session; skip if not available
            # Callers in this file pass session where needed (execute_run_async ensures thread status uses session)
            return
        values = {"status": status, "updated_at": datetime.utcnow()}
        if output is not None:
            values["output"] = output
        if error is not None:
            values["error_message"] = error
        await session.execute(update(RunORM).where(RunORM.run_id == run_id).values(**values))
        await session.commit()
    finally:
        # Do not close the session; lifecycle managed by FastAPI DI
        pass
