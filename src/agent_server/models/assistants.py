"""Assistant-related Pydantic models for Agent Protocol"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AssistantCreate(BaseModel):
    """Request model for creating assistants"""
    assistant_id: str = Field(..., description="Unique assistant identifier")
    name: str = Field(..., description="Human-readable assistant name")
    description: Optional[str] = Field(None, description="Assistant description")
    config: Optional[Dict[str, Any]] = Field(None, description="Assistant configuration")
    graph_id: Optional[str] = Field(None, description="LangGraph graph ID from langgraph.json")


class Assistant(BaseModel):
    """Assistant entity model"""
    assistant_id: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    graph_id: str
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class AssistantList(BaseModel):
    """Response model for listing assistants"""
    assistants: list[Assistant]
    total: int


class AgentSchemas(BaseModel):
    """Agent schema definitions for client integration"""
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent inputs")
    output_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent outputs") 
    state_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent state")
    config_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent config")