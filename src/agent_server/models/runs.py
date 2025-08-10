"""Run-related Pydantic models for Agent Protocol"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """Request model for creating runs"""
    assistant_id: str = Field(..., description="Assistant to execute")
    input: Dict[str, Any] = Field(..., description="Input data for the run")
    config: Optional[Dict[str, Any]] = Field(None, description="LangGraph execution config")
    checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="Checkpoint configuration (e.g., {'checkpoint_id': '...', 'checkpoint_ns': ''})",
    )
    stream: bool = Field(False, description="Enable streaming response")
    stream_mode: Optional[str | list[str]] = Field(None, description="Requested stream mode(s) as per LangGraph")


class Run(BaseModel):
    """Run entity model"""
    run_id: str
    thread_id: str
    assistant_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RunList(BaseModel):
    """Response model for listing runs"""
    runs: List[Run]
    total: int


class RunStatus(BaseModel):
    """Simple run status response"""
    run_id: str
    status: str
    message: Optional[str] = None
