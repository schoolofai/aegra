"""Run endpoints for Agent Protocol"""
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Query
import logging
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.orm import Assistant as AssistantORM, Thread as ThreadORM, get_session
from fastapi.responses import StreamingResponse

from ..models import Run, RunCreate, RunList, RunStatus, User
from ..core.auth_deps import get_current_user
from ..core.sse import get_sse_headers
from ..services.langgraph_service import get_langgraph_service

router = APIRouter()

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
    print(f"create_run: scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}")
    print(f"[create_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}")

    # Validate assistant exists and get its graph_id (IDs are plain strings)
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == str(request.assistant_id),
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
        run_id=run_id,  # explicitly set (DB can also default-generate if omitted)
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
    print(f"[create_run] background task created task_id={id(task)} for run_id={run_id}")
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
    print(f"[create_and_stream_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}")

    # Validate assistant exists and get its graph_id (IDs are plain strings)
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == str(request.assistant_id),
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
    print(f"[create_and_stream_run] background task created task_id={id(task)} for run_id={run_id}")
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
        RunORM.run_id == str(run_id),
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
    )
    print(f"[get_run] querying DB run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(stmt)
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    print(f"[get_run] found run status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}")
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
    print(f"[list_runs] querying DB thread_id={thread_id} user={user.identity}")
    result = await session.scalars(stmt)
    rows = result.all()
    runs = [Run.model_validate({c.name: getattr(r, c.name) for c in r.__table__.columns}) for r in rows]
    print(f"[list_runs] total={len(runs)} user={user.identity} thread_id={thread_id}")
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
    print(f"[update_run] fetch for update run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Handle interruption/cancellation
    from ..services.streaming_service import streaming_service

    if request.status == "cancelled":
        print(f"[update_run] cancelling run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.cancel_run(run_id)
        print(f"[update_run] set DB status=cancelled run_id={run_id}")
        await session.execute(
            update(RunORM).where(RunORM.run_id == str(run_id)).values(status="cancelled", updated_at=datetime.utcnow())
        )
        await session.commit()
        print(f"[update_run] commit done (cancelled) run_id={run_id}")
    elif request.status == "interrupted":
        print(f"[update_run] interrupt run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.interrupt_run(run_id)
        print(f"[update_run] set DB status=interrupted run_id={run_id}")
        await session.execute(
            update(RunORM).where(RunORM.run_id == str(run_id)).values(status="interrupted", updated_at=datetime.utcnow())
        )
        await session.commit()
        print(f"[update_run] commit done (interrupted) run_id={run_id}")

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
    print(f"[join_run] fetch for join run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    print(f"[join_run] current status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}")

    # Wait for completion if not finished
    if run_orm.status not in ["completed", "failed", "cancelled"]:
        task = active_runs.get(run_id)
        print(f"[join_run] active_runs has task={bool(task)} run_id={run_id}")
        if task:
            try:
                print(f"[join_run] awaiting task_id={id(task)} run_id={run_id}")
                await task  # Wait for completion
                print(f"[join_run] task completed run_id={run_id}")
            except asyncio.CancelledError:
                print(f"[join_run] task cancelled run_id={run_id}")
            except Exception as e:
                print(f"[join_run] task errored run_id={run_id} error={e}")

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
    print(f"[stream_run] fetch for stream run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    print(f"[stream_run] status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}")
    # If already terminal, emit a final end event
    if run_orm.status in ["completed", "failed", "cancelled"]:
        from ..core.sse import create_end_event

        async def generate_final():
            yield create_end_event()

        print(f"[stream_run] starting terminal stream run_id={run_id} status={run_orm.status}")
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

    # Build a lightweight Pydantic Run from ORM for streaming context (IDs already strings)
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
    print(f"[cancel_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}")
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

    if action == "interrupt":
        print(f"[cancel_run] interrupt run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.interrupt_run(run_id)
        # Persist status as interrupted
        await session.execute(
            update(RunORM).where(RunORM.run_id == str(run_id)).values(status="interrupted", updated_at=datetime.utcnow())
        )
        await session.commit()
    else:
        print(f"[cancel_run] cancel run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.cancel_run(run_id)
        # Persist status as cancelled
        await session.execute(
            update(RunORM).where(RunORM.run_id == str(run_id)).values(status="cancelled", updated_at=datetime.utcnow())
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

    # Reload and return updated Run (do NOT delete here; deletion is a separate endpoint)
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found after cancellation")
    return Run.model_validate({c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns})


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
        print(f"[execute_run_async] ENTER run_id={run_id} thread_id={thread_id} graph_id={graph_id}")
        # Update status
        await update_run_status(run_id, "running", session=session)
        print(f"[execute_run_async] status->running run_id={run_id}")
        
        # Get graph and execute
        langgraph_service = get_langgraph_service()
        print(f"[execute_run_async] fetching graph graph_id={graph_id}")
        graph = await langgraph_service.get_graph(graph_id)
        print(f"[execute_run_async] graph fetched graph_id={graph_id} type={type(graph)}")
        
        from ..services.langgraph_service import create_run_config
        run_config = create_run_config(run_id, thread_id, user, config or {})
        print(f"[execute_run_async] run_config created stream_mode={stream_mode or RUN_STREAM_MODES}")
        
        # Always execute using streaming to capture events for later replay
        event_counter = 0
        final_output = None
        # Use streaming service's broker system to distribute events
        from ..core.auth_ctx import with_auth_ctx
        async with with_auth_ctx(user, []):
            print(f"[execute_run_async] entering astream loop run_id={run_id}")
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
        print(f"[execute_run_async] signalling end id={end_event_id}")
        
        await streaming_service.put_to_broker(run_id, end_event_id, end_event)
        await streaming_service.store_event_from_raw(run_id, end_event_id, end_event)
        
        # Update with results (store empty JSON to avoid serialization issues for now)
        await update_run_status(run_id, "completed", output={}, session=session)
        print(f"[execute_run_async] COMPLETED run_id={run_id} thread_id={thread_id}")
        # Mark thread back to idle
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        print(f"[execute_run_async] thread status set idle thread_id={thread_id}")
        
    except asyncio.CancelledError:
        print(f"[execute_run_async] CANCELLED run_id={run_id}")
        # Store empty output to avoid JSON serialization issues
        await update_run_status(run_id, "cancelled", output={}, session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        print(f"[execute_run_async] cancelled run_id={run_id} thread_id={thread_id}")
        # Signal cancellation to broker
        await streaming_service.signal_run_cancelled(run_id)
        raise
    except Exception as e:
        print(f"[execute_run_async] EXCEPTION run_id={run_id} error={e}")
        # Store empty output to avoid JSON serialization issues
        await update_run_status(run_id, "failed", output={}, error=str(e), session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status")
        await set_thread_status(session, thread_id, "idle")
        print(f"[execute_run_async] FAILED run_id={run_id} thread_id={thread_id} error={e}")
        # Signal error to broker
        await streaming_service.signal_run_error(run_id, str(e))
        raise
    finally:
        # Clean up broker
        print(f"[execute_run_async] cleaning up broker and active_runs run_id={run_id}")
        await streaming_service.cleanup_run(run_id)
        active_runs.pop(run_id, None)
        print(f"[execute_run_async] cleanup done run_id={run_id}")


async def update_run_status(
    run_id: str,
    status: str,
    output=None,
    error: str = None,
    session: Optional[AsyncSession] = None,
):
    """Update run status in database (persisted). If session not provided, opens a short-lived session."""
    from ..core.orm import Run as RunORM
    from ..core.orm import _get_session_maker  # use internal session factory when out of request context

    owns_session = False
    if session is None:
        maker = _get_session_maker()
        session = maker()  # type: ignore[assignment]
        owns_session = True
    try:
        values = {"status": status, "updated_at": datetime.utcnow()}
        if output is not None:
            values["output"] = output
        if error is not None:
            values["error_message"] = error
        print(f"[update_run_status] updating DB run_id={run_id} keys={list(values.keys())}")
        await session.execute(update(RunORM).where(RunORM.run_id == str(run_id)).values(**values))  # type: ignore[arg-type]
        await session.commit()
        print(f"[update_run_status] commit done run_id={run_id}")
    finally:
        # Close only if we created it here
        if owns_session:
            await session.close()  # type: ignore[func-returns-value]


@router.delete("/threads/{thread_id}/runs/{run_id}", status_code=204)
async def delete_run(
    thread_id: str,
    run_id: str,
    force: int = Query(0, ge=0, le=1, description="Force cancel active run before delete (1=yes)"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a run record.

    Behavior:
    - If the run is active (pending/running/streaming) and force=0, returns 409 Conflict.
    - If force=1 and the run is active, cancels it first (best-effort) and then deletes.
    - Always returns 204 No Content on successful deletion.
    """
    from ..core.orm import Run as RunORM
    print(f"[delete_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # If active and not forcing, reject deletion
    if run_orm.status in ["pending", "running", "streaming"] and not force:
        raise HTTPException(
            status_code=409,
            detail="Run is active. Retry with force=1 to cancel and delete.",
        )

    # If forcing and active, cancel first
    if force and run_orm.status in ["pending", "running", "streaming"]:
        from ..services.streaming_service import streaming_service
        print(f"[delete_run] force-cancelling active run run_id={run_id}")
        await streaming_service.cancel_run(run_id)
        # Best-effort: wait for bg task to settle
        task = active_runs.get(run_id)
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    # Delete the record
    await session.execute(
        delete(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    await session.commit()

    # Clean up active task if exists
    task = active_runs.pop(run_id, None)
    if task and not task.done():
        task.cancel()

    # 204 No Content
    return
