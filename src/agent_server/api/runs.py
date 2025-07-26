"""Run endpoints for Agent Protocol"""
import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse

from ..models import Run, RunCreate, RunList, RunStatus, User
from ..core.auth_deps import get_current_user
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
    
    # Create and track background task
    task = asyncio.create_task(
        execute_run_async(run_id, thread_id, request, langgraph_service, user)
    )
    active_runs[run_id] = task
    
    # Clean up task reference when done
    def cleanup_task(future):
        active_runs.pop(run_id, None)
    task.add_done_callback(cleanup_task)
    
    return run


@router.post("/threads/{thread_id}/runs/stream")
async def create_and_stream_run(
    thread_id: str, 
    request: RunCreate,
    user: User = Depends(get_current_user)
):
    """Create a new run and stream its execution"""
    
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
    
    # Start streaming immediately
    from ..services.streaming_service import streaming_service
    from ..core.sse import get_sse_headers
    
    return StreamingResponse(
        streaming_service.stream_run_execution(run, user, None, request.config),
        media_type="text/event-stream",
        headers=get_sse_headers()
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


@router.post("/threads/{thread_id}/runs/{run_id}/cancel", response_model=RunStatus)
async def cancel_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Cancel a running or pending run"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Check if cancellable
    if run.status in ["completed", "failed", "cancelled"]:
        raise HTTPException(400, f"Cannot cancel run with status: {run.status}")
    
    # Use streaming service for proper cancellation
    from ..services.streaming_service import streaming_service
    success = await streaming_service.cancel_run(run_id)
    
    if success:
        return RunStatus(run_id=run_id, status="cancelled", message="Run cancelled")
    else:
        raise HTTPException(500, "Failed to cancel run")


@router.post("/threads/{thread_id}/runs/{run_id}/interrupt", response_model=RunStatus)
async def interrupt_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Interrupt a running execution gracefully"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Check if interruptible
    if run.status not in ["running", "streaming"]:
        raise HTTPException(400, f"Cannot interrupt run with status: {run.status}")
    
    # Use streaming service for proper interruption
    from ..services.streaming_service import streaming_service
    success = await streaming_service.interrupt_run(run_id)
    
    if success:
        return RunStatus(run_id=run_id, status="interrupted", message="Run interrupted")
    else:
        raise HTTPException(500, "Failed to interrupt run")


@router.get("/threads/{thread_id}/runs/{run_id}/wait", response_model=Run)
async def wait_for_run(thread_id: str, run_id: str, user: User = Depends(get_current_user)):
    """Wait for a background run to complete and return final output"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # If already finished, return immediately
    if run.status in ["completed", "failed", "cancelled"]:
        return run
    
    # Wait for background task if running
    task = active_runs.get(run_id)
    if task:
        try:
            await task  # Wait for completion
        except asyncio.CancelledError:
            pass  # Task was cancelled
        except Exception:
            pass  # Task failed, status already updated
    
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
    user: User = Depends(get_current_user)
):
    """Stream run execution with SSE and reconnection support"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity or run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    # Check if run is streamable
    if run.status in ["completed", "failed", "cancelled"]:
        # Return final state for completed runs
        from ..core.sse import get_sse_headers, format_sse_event
        
        async def generate_final():
            yield format_sse_event(
                id=f"{run_id}_final",
                event="complete",
                data={
                    "type": "run_complete",
                    "run_id": run_id,
                    "status": run.status,
                    "final_output": run.output
                }
            )
        
        return StreamingResponse(
            generate_final(),
            media_type="text/event-stream",
            headers=get_sse_headers()
        )
    
    # Stream active or pending runs
    from ..services.streaming_service import streaming_service
    from ..core.sse import get_sse_headers
    
    return StreamingResponse(
        streaming_service.stream_run_execution(run, user, last_event_id, run.config),
        media_type="text/event-stream",
        headers=get_sse_headers()
    )


@router.get("/threads/{thread_id}/runs/{run_id}/join_stream")
async def join_stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    user: User = Depends(get_current_user)
):
    """Join stream for an existing run - SDK compatibility endpoint"""
    # This is the same as stream_run but with different URL for SDK compatibility
    return await stream_run(thread_id, run_id, last_event_id, user)


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
    request: RunCreate,
    langgraph_service,
    user: User
):
    """Execute run with LangGraph service"""
    try:
        # Update to running
        await update_run_status(run_id, "running")
        
        # Get assistant to find the correct graph_id
        from .assistants import _assistants_db
        assistant = _assistants_db[request.assistant_id]
        
        # Load graph using the assistant's graph_id
        graph = await langgraph_service.get_graph(assistant.graph_id)
        
        # Prepare LangGraph config
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user.identity,
                "assistant_id": request.assistant_id
            }
        }
        
        # Add custom config if provided
        if request.config:
            config["configurable"].update(request.config)
        
        # Execute graph
        result = await graph.ainvoke(request.input, config=config)
        
        # Update with success
        await update_run_status(run_id, "completed", output=result)
        
    except asyncio.CancelledError:
        await update_run_status(run_id, "cancelled")
        raise
    except Exception as e:
        await update_run_status(run_id, "failed", error=str(e))


async def update_run_status(run_id: str, status: str, output=None, error=None):
    """Update run status in database"""
    if run_id in _runs_db:
        run = _runs_db[run_id]
        run.status = status
        run.updated_at = datetime.utcnow()
        
        if output is not None:
            run.output = output
        
        if error is not None:
            run.error_message = error