"""Run endpoints for Agent Protocol"""
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.orm import Assistant as AssistantORM, get_session
from fastapi.responses import StreamingResponse

from ..models import Run, RunCreate, RunList, RunStatus, User
from ..core.auth_deps import get_current_user
from ..core.sse import get_sse_headers
from ..services.langgraph_service import get_langgraph_service

router = APIRouter()


# Simple in-memory storage for now
_runs_db = {}

# Global task registry for run management
active_runs: Dict[str, asyncio.Task] = {}

# Default stream modes for background run execution
RUN_STREAM_MODES = ["messages", "values", "custom"]


@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create and execute a new run"""
    
    run_id = str(uuid4())
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    # Validate assistant exists and get its graph_id
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == request.assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")
    
    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")
    
    # Create run record
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=request.assistant_id,
        status="pending",
        input=request.input,
        config=request.config,
        user_id=user.identity,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    _runs_db[run_id] = run
    
    # Start execution asynchronously
    task = asyncio.create_task(execute_run_async(run_id, thread_id, assistant.graph_id, request.input, user, request.config, request.stream_mode))
    active_runs[run_id] = task
    
    return run


@router.post("/threads/{thread_id}/runs/stream")
async def create_and_stream_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create a new run and stream its execution - LangGraph compatible"""
    
    run_id = str(uuid4())
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    # Validate assistant exists and get its graph_id
    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == request.assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")
    
    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")
    
    # Create run record
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=request.assistant_id,
        status="streaming",
        input=request.input,
        config=request.config,
        user_id=user.identity,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    _runs_db[run_id] = run
    
    # Start background execution that will populate the broker
    task = asyncio.create_task(execute_run_async(run_id, thread_id, assistant.graph_id, request.input, user, request.config, request.stream_mode))
    active_runs[run_id] = task
    
    # Extract requested stream mode(s) - not used for broker consumption but kept for compatibility
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
async def get_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Get run by ID"""
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    return run


@router.get("/threads/{thread_id}/runs", response_model=RunList)
async def list_runs(thread_id: str, user: User = Depends(get_current_user)):
    """List runs for a specific thread"""
    user_runs = [r for r in _runs_db.values() 
                 if r.user_id == user.identity and r.thread_id == thread_id]
    return RunList(
        runs=user_runs,
        total=len(user_runs)
    )


@router.patch("/threads/{thread_id}/runs/{run_id}")
async def update_run(
    thread_id: str, 
    run_id: str, 
    request: RunStatus,
    user: User = Depends(get_current_user)
):
    """Update run status (for cancellation/interruption)"""
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Handle interruption/cancellation
    from ..services.streaming_service import streaming_service
    
    if request.status == "cancelled":
        await streaming_service.cancel_run(run_id)
    elif request.status == "interrupted":
        await streaming_service.interrupt_run(run_id)
    
    # Return final run state  
    return _runs_db[run_id]


@router.get("/threads/{thread_id}/runs/{run_id}/join")
async def join_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Join a run (wait for completion and return thread state) - SDK compatibility"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Wait for completion if not finished
    if run.status not in ["completed", "failed", "cancelled"]:
        task = active_runs.get(run_id)
        if task:
            try:
                await task  # Wait for completion
            except asyncio.CancelledError:
                pass  # Task was cancelled
            except Exception:
                pass  # Task failed, status already updated
    
    # Return the final thread state (which should include the run output)
    final_run = _runs_db[run_id]
    return final_run.output if final_run.output else {}


@router.get("/threads/{thread_id}/runs/{run_id}/stream")
async def stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    stream_mode: Optional[str] = Query(None),
    user: User = Depends(get_current_user)
):
    """Stream run execution with SSE and reconnection support - LangGraph compatible"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Check if run is streamable
    if run.status in ["completed", "failed", "cancelled"]:
        # Return final state for completed runs using new event format
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
    
    # Stream active or pending runs
    from ..services.streaming_service import streaming_service
    
    return StreamingResponse(
        streaming_service.stream_run_execution(run, user, last_event_id, run.config, stream_mode),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream", 
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        }
    )



@router.delete("/threads/{thread_id}/runs/{run_id}")
async def delete_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Delete a run"""
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Cancel the run if it's still active
    if run.status in ["pending", "running", "streaming"]:
        from ..services.streaming_service import streaming_service
        await streaming_service.cancel_run(run_id)
    
    # Remove from database
    del _runs_db[run_id]
    
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
    stream_mode: Optional[list[str]] = None
):
    """Execute run asynchronously in background using streaming to capture all events"""
    from ..services.streaming_service import streaming_service
    
    try:
        # Update status
        await update_run_status(run_id, "running")
        
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
        await update_run_status(run_id, "completed", output=final_output)
        
    except asyncio.CancelledError:
        await update_run_status(run_id, "cancelled")
        # Signal cancellation to broker
        await streaming_service.signal_run_cancelled(run_id)
        raise
    except Exception as e:
        await update_run_status(run_id, "failed", error=str(e))
        # Signal error to broker
        await streaming_service.signal_run_error(run_id, str(e))
        raise
    finally:
        # Clean up broker
        await streaming_service.cleanup_run(run_id)
        active_runs.pop(run_id, None)


async def update_run_status(run_id: str, status: str, output=None, error: str = None):
    """Update run status in database"""
    if run_id in _runs_db:
        run = _runs_db[run_id]
        run.status = status
        run.updated_at = datetime.utcnow()
        if output is not None:
            run.output = output
        if error is not None:
            run.error_message = error
        _runs_db[run_id] = run