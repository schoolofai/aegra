"""Thread-related Pydantic models for Agent Protocol"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    """Request model for creating threads"""
    metadata: Optional[Dict[str, Any]] = Field(None, description="Thread metadata")
    initial_state: Optional[Dict[str, Any]] = Field(None, description="LangGraph initial state")


class Thread(BaseModel):
    """Thread entity model"""
    thread_id: str
    status: str = "idle"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ThreadList(BaseModel):
    """Response model for listing threads"""
    threads: List[Thread]
    total: int


class ThreadSearchRequest(BaseModel):
    """Request model for thread search"""
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    status: Optional[str] = Field(None, description="Thread status filter")
    limit: Optional[int] = Field(20, le=100, ge=1, description="Maximum results")
    offset: Optional[int] = Field(0, ge=0, description="Results offset")
    order_by: Optional[str] = Field("created_at DESC", description="Sort order")


class ThreadSearchResponse(BaseModel):
    """Response model for thread search"""
    threads: List[Thread]
    total: int
    limit: int
    offset: int