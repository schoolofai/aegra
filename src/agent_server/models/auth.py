"""Authentication and user context models"""
from typing import Optional, List
from pydantic import BaseModel


class User(BaseModel):
    """User context model for authentication"""
    identity: str
    display_name: Optional[str] = None
    permissions: List[str] = []
    org_id: Optional[str] = None
    is_authenticated: bool = True


class AuthContext(BaseModel):
    """Authentication context for request processing"""
    user: User
    request_id: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True


class TokenPayload(BaseModel):
    """JWT token payload structure"""
    sub: str  # subject (user ID)
    name: Optional[str] = None
    scopes: List[str] = []
    org: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None