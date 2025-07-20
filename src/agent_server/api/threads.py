"""Thread endpoints for Agent Protocol"""
from uuid import uuid4
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from ..models import Thread, ThreadCreate, ThreadList, ThreadSearchRequest, ThreadSearchResponse, User
from ..core.auth_deps import get_current_user

router = APIRouter()


# Simple in-memory storage for now
_threads_db = {}


@router.post("/threads", response_model=Thread)
async def create_thread(request: ThreadCreate, user: User = Depends(get_current_user)):
    """Create a new conversation thread"""
    
    thread_id = str(uuid4())
    
    # Create thread record
    thread = Thread(
        thread_id=thread_id,
        status="idle",
        metadata=request.metadata or {},
        user_id=user.identity,
        created_at=datetime.utcnow()
    )
    
    _threads_db[thread_id] = thread
    
    # Initialize LangGraph checkpoint if initial_state provided
    if request.initial_state:
        # TODO: Initialize LangGraph checkpoint with initial state
        pass
    
    return thread


@router.get("/threads", response_model=ThreadList)
async def list_threads(user: User = Depends(get_current_user)):
    """List user's threads"""
    user_threads = [t for t in _threads_db.values() if t.user_id == user.identity]
    return ThreadList(
        threads=user_threads,
        total=len(user_threads)
    )


@router.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(thread_id: str, user: User = Depends(get_current_user)):
    """Get thread by ID"""
    if thread_id not in _threads_db:
        raise HTTPException(404, f"Thread '{thread_id}' not found")
    
    thread = _threads_db[thread_id]
    if thread.user_id != user.identity:
        raise HTTPException(404, f"Thread '{thread_id}' not found")
    
    return thread


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, user: User = Depends(get_current_user)):
    """Delete thread by ID"""
    if thread_id not in _threads_db:
        raise HTTPException(404, f"Thread '{thread_id}' not found")
    
    thread = _threads_db[thread_id]
    if thread.user_id != user.identity:
        raise HTTPException(404, f"Thread '{thread_id}' not found")
    
    del _threads_db[thread_id]
    return {"status": "deleted"}


@router.post("/threads/search", response_model=ThreadSearchResponse)
async def search_threads(request: ThreadSearchRequest, user: User = Depends(get_current_user)):
    """Search threads with filters"""
    
    # Start with user's threads only
    threads = [t for t in _threads_db.values() if t.user_id == user.identity]
    
    # Apply filters
    if request.status:
        threads = [t for t in threads if t.status == request.status]
    
    if request.metadata:
        # Simple metadata matching
        for key, value in request.metadata.items():
            threads = [t for t in threads if t.metadata.get(key) == value]
    
    # Apply pagination
    total = len(threads)
    offset = request.offset or 0
    limit = request.limit or 20
    
    threads = threads[offset:offset + limit]
    
    return ThreadSearchResponse(
        threads=threads,
        total=total,
        limit=limit,
        offset=offset
    )