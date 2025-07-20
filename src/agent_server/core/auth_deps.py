"""Authentication dependencies for FastAPI endpoints"""
from fastapi import Request, HTTPException
from typing import Optional

from ..models.auth import User


async def get_current_user(request: Request) -> User:
    """Extract current user from request context"""
    
    # LangGraph SDK Auth should have set this in the request context
    # For now, simulate the user extraction
    
    # Get authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        # Default to anonymous user for now
        return User(
            identity="anonymous",
            display_name="Anonymous User",
            permissions=[],
            org_id="public"
        )
    
    if auth_header == "Bearer dev-token":
        return User(
            identity="dev-user",
            display_name="Development User", 
            permissions=["admin"],
            org_id="dev-org"
        )
    
    # For other tokens, extract user info (integrate with LangGraph SDK Auth)
    return User(
        identity="test-user",
        display_name="Test User",
        permissions=["user"],
        org_id="test-org"
    )


def get_user_id(user: User) -> str:
    """Helper to get user ID safely"""
    return user.identity