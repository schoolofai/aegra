"""Simple authentication configuration for LangGraph Agent Server"""
from langgraph_sdk import Auth

auth = Auth()


@auth.authenticate
async def authenticate(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Simple authentication that allows everything"""
    return {
        "identity": "dev-user",
        "display_name": "Development User",
        "permissions": ["admin"]
    }


@auth.on
async def authorize_request(ctx, value):
    """Simple authorization that allows everything"""
    return True