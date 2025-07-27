"""Run endpoints for Agent Protocol"""
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Query
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


@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_run(
    thread_id: str, 
    request: RunCreate,
    user: User = Depends(get_current_user)
):
    """Create and execute a new run"""
    
    run_id = str(uuid4())
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    # Validate assistant exists and get its graph_id
    from .assistants import _assistants_db
    if request.assistant_id not in _assistants_db:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")
    
    assistant = _assistants_db[request.assistant_id]
    if assistant.user_id != user.identity:
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
    task = asyncio.create_task(execute_run_async(run_id, thread_id, assistant.graph_id, request.input, user, request.config))
    active_runs[run_id] = task
    
    return run


@router.post("/threads/{thread_id}/runs/stream")
async def create_and_stream_run(
    thread_id: str, 
    request: RunCreate,
    user: User = Depends(get_current_user)
):
    """Create a new run and stream its execution - LangGraph compatible"""
    
    run_id = str(uuid4())
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    # Validate assistant exists and get its graph_id
    from .assistants import _assistants_db
    if request.assistant_id not in _assistants_db:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")
    
    assistant = _assistants_db[request.assistant_id]
    if assistant.user_id != user.identity:
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
    
    # Extract requested stream mode(s)
    stream_mode = request.stream_mode
    if not stream_mode and request.config and "stream_mode" in request.config:
        stream_mode = request.config["stream_mode"]
    
    # Start streaming immediately using EventSourceResponse
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


@router.get("/threads/{thread_id}/runs/{run_id}/join_stream")
async def join_stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    stream_mode: Optional[str] = Query(None),
    user: User = Depends(get_current_user)
):
    """Join stream for an existing run - SDK compatibility endpoint"""
    # This is the same as stream_run but with different URL for SDK compatibility
    return await stream_run(thread_id, run_id, last_event_id, stream_mode, user)


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
    config: Optional[dict] = None
):
    """Execute run asynchronously in background"""
    try:
        # Update status
        await update_run_status(run_id, "running")
        
        # Get graph and execute
        langgraph_service = get_langgraph_service()
        graph = await langgraph_service.get_graph(graph_id)
        
        from ..services.langgraph_service import create_run_config
        run_config = create_run_config(run_id, thread_id, user, config or {})
        
        # Execute the graph
        result = await graph.ainvoke(input_data, config=run_config)
        
        # Update with results
        await update_run_status(run_id, "completed", output=result)
        
    except asyncio.CancelledError:
        await update_run_status(run_id, "cancelled")
        raise
    except Exception as e:
        await update_run_status(run_id, "failed", error=str(e))
        raise
    finally:
        # Clean up
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