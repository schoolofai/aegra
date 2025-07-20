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
    
    # Validate assistant exists
    available_graphs = langgraph_service.list_graphs()
    if request.assistant_id not in available_graphs:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")
    
    # Create run record
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=request.assistant_id,
        status="pending",
        input=request.input,
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


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, user: User = Depends(get_current_user)):
    """Get run by ID"""
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    return run


@router.get("/runs", response_model=RunList)
async def list_runs(user: User = Depends(get_current_user)):
    """List user's runs"""
    user_runs = [r for r in _runs_db.values() if r.user_id == user.identity]
    return RunList(
        runs=user_runs,
        total=len(user_runs)
    )


@router.post("/runs/{run_id}/cancel", response_model=RunStatus)
async def cancel_run(run_id: str, user: User = Depends(get_current_user)):
    """Cancel a running or pending run"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity:
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


@router.post("/runs/{run_id}/interrupt", response_model=RunStatus)
async def interrupt_run(run_id: str, user: User = Depends(get_current_user)):
    """Interrupt a running execution gracefully"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity:
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


@router.get("/runs/{run_id}/wait", response_model=Run)
async def wait_for_run(run_id: str, user: User = Depends(get_current_user)):
    """Wait for a background run to complete and return final output"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity:
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


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    user: User = Depends(get_current_user)
):
    """Stream run execution with SSE and reconnection support"""
    
    if run_id not in _runs_db:
        raise HTTPException(404, f"Run '{run_id}' not found")
    
    run = _runs_db[run_id]
    if run.user_id != user.identity:
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
        streaming_service.stream_run_execution(run, user, last_event_id),
        media_type="text/event-stream",
        headers=get_sse_headers()
    )


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
        
        # Load graph
        graph = await langgraph_service.get_graph(request.assistant_id)
        
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