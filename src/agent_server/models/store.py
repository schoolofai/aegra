"""Store-related Pydantic models for Agent Protocol"""
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class StorePutRequest(BaseModel):
    """Request model for storing items"""
    namespace: List[str] = Field(..., description="Storage namespace")
    key: str = Field(..., description="Item key")
    value: Any = Field(..., description="Item value")


class StoreGetResponse(BaseModel):
    """Response model for getting items"""
    key: str
    value: Any
    namespace: List[str]


class StoreSearchRequest(BaseModel):
    """Request model for searching store items"""
    namespace_prefix: List[str] = Field(..., description="Namespace prefix to search")
    query: Optional[str] = Field(None, description="Search query")
    limit: Optional[int] = Field(20, le=100, ge=1, description="Maximum results")
    offset: Optional[int] = Field(0, ge=0, description="Results offset")


class StoreItem(BaseModel):
    """Store item model"""
    key: str
    value: Any
    namespace: List[str]


class StoreSearchResponse(BaseModel):
    """Response model for store search"""
    items: List[StoreItem]
    total: int
    limit: int
    offset: int


class StoreDeleteRequest(BaseModel):
    """Request body for deleting store items (SDK-compatible)."""
    namespace: List[str]
    key: str