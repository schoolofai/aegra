"""Thread endpoints for Agent Protocol"""
from uuid import uuid4
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Thread, ThreadCreate, ThreadList, ThreadSearchRequest, ThreadSearchResponse, User
from ..core.auth_deps import get_current_user
from ..core.orm import Thread as ThreadORM, get_session

router = APIRouter()


# In-memory storage removed; using database via ORM


@router.post("/threads", response_model=Thread)
async def create_thread(
    request: ThreadCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create a new conversation thread"""
    
    thread_id = str(uuid4())

    # Build metadata with required fields
    metadata = request.metadata or {}
    metadata.update({
        "owner": user.identity,
        "assistantId": None,  # Will be set when first run is created
        "graphId": None,       # Will be set when first run is created  
        "threadName": "",      # User can update this later
    })
    
    thread_orm = ThreadORM(
        thread_id=thread_id,
        status="idle",
        metadata_json=metadata,
        user_id=user.identity,
    )
    session.add(thread_orm)
    await session.commit()
    await session.refresh(thread_orm)

    # TODO: initialize LangGraph checkpoint with initial_state if provided

    return Thread.model_validate({
        **{c.name: getattr(thread_orm, c.name) for c in thread_orm.__table__.columns},
        "metadata": thread_orm.metadata_json,
    })


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """List user's threads"""
    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)
    result = await session.scalars(stmt)
    user_threads = [
        Thread.model_validate({
            **{c.name: getattr(t, c.name) for c in t.__table__.columns},
            "metadata": t.metadata_json,
        })
        for t in result.all()
    ]
    return ThreadList(threads=user_threads, total=len(user_threads))


@router.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get thread by ID"""
    stmt = select(ThreadORM).where(ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity)
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    return Thread.model_validate({
        **{c.name: getattr(thread, c.name) for c in thread.__table__.columns},
        "metadata": thread.metadata_json,
    })


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Delete thread by ID"""
    stmt = select(ThreadORM).where(ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity)
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    await session.delete(thread)
    await session.commit()
    return {"status": "deleted"}


@router.post("/threads/search", response_model=ThreadSearchResponse)
async def search_threads(
    request: ThreadSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Search threads with filters"""
    
    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)

    if request.status:
        stmt = stmt.where(ThreadORM.status == request.status)

    if request.metadata:
        # For each key/value, filter JSONB field
        for key, value in request.metadata.items():
            stmt = stmt.where(ThreadORM.metadata_json[key].as_string() == str(value))

    # Count total first
    total = len(await session.scalars(stmt).all())

    offset = request.offset or 0
    limit = request.limit or 20
    stmt = stmt.offset(offset).limit(limit)

    result = await session.scalars(stmt)
    threads_models = [
        Thread.model_validate({
            **{c.name: getattr(t, c.name) for c in t.__table__.columns},
            "metadata": t.metadata_json,
        })
        for t in result.all()
    ]

    return ThreadSearchResponse(
        threads=threads_models,
        total=total,
        limit=limit,
        offset=offset,
    )