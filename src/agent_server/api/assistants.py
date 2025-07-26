"""Assistant endpoints for Agent Protocol"""
from uuid import uuid4
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from ..models import Assistant, AssistantCreate, AssistantList, AssistantSearchRequest, AssistantSearchResponse, AgentSchemas, User
from ..services.langgraph_service import get_langgraph_service
from ..core.auth_deps import get_current_user

router = APIRouter()


# Simple in-memory storage for now
_assistants_db = {}


@router.post("/assistants", response_model=Assistant)
async def create_assistant(
    request: AssistantCreate,
    user: User = Depends(get_current_user)
):
    """Create a new assistant"""
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    # Validate graph exists in langgraph.json
    available_graphs = langgraph_service.list_graphs()
    graph_id = request.graph_id or request.assistant_id
    
    if graph_id not in available_graphs:
        raise HTTPException(
            400,
            f"Graph '{graph_id}' not found in langgraph.json. Available: {list(available_graphs.keys())}"
        )
    
    # Validate graph can be loaded
    try:
        graph = await langgraph_service.get_graph(graph_id)
    except Exception as e:
        raise HTTPException(400, f"Failed to load graph: {str(e)}")
    
    # Check if assistant already exists
    if request.assistant_id in _assistants_db:
        raise HTTPException(409, f"Assistant '{request.assistant_id}' already exists")
    
    # Create assistant record
    assistant = Assistant(
        assistant_id=request.assistant_id,
        name=request.name,
        description=request.description,
        config=request.config or {},
        graph_id=graph_id,
        user_id=user.identity,
        created_at=datetime.utcnow()
    )
    
    _assistants_db[request.assistant_id] = assistant
    
    return assistant


@router.get("/assistants", response_model=AssistantList)
async def list_assistants(user: User = Depends(get_current_user)):
    """List user's assistants"""
    # Filter assistants by user
    user_assistants = [a for a in _assistants_db.values() if a.user_id == user.identity]
    return AssistantList(
        assistants=user_assistants,
        total=len(user_assistants)
    )


@router.post("/assistants/search", response_model=AssistantSearchResponse)
async def search_assistants(
    request: AssistantSearchRequest,
    user: User = Depends(get_current_user)
):
    """Search assistants with filters"""
    # Start with user's assistants
    user_assistants = [a for a in _assistants_db.values() if a.user_id == user.identity]
    
    # Apply filters
    filtered_assistants = user_assistants
    
    if request.name:
        filtered_assistants = [
            a for a in filtered_assistants 
            if request.name.lower() in a.name.lower()
        ]
    
    if request.description:
        filtered_assistants = [
            a for a in filtered_assistants 
            if a.description and request.description.lower() in a.description.lower()
        ]
    
    if request.graph_id:
        filtered_assistants = [
            a for a in filtered_assistants 
            if a.graph_id == request.graph_id
        ]
    
    # Apply pagination
    total = len(filtered_assistants)
    offset = request.offset or 0
    limit = request.limit or 20
    
    paginated_assistants = filtered_assistants[offset:offset + limit]
    
    return AssistantSearchResponse(
        assistants=paginated_assistants,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/assistants/{assistant_id}", response_model=Assistant)
async def get_assistant(assistant_id: str, user: User = Depends(get_current_user)):
    """Get assistant by ID"""
    if assistant_id not in _assistants_db:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    assistant = _assistants_db[assistant_id]
    if assistant.user_id != user.identity:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    return assistant


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: str, user: User = Depends(get_current_user)):
    """Delete assistant by ID"""
    if assistant_id not in _assistants_db:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    assistant = _assistants_db[assistant_id]
    if assistant.user_id != user.identity:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    del _assistants_db[assistant_id]
    return {"status": "deleted"}


@router.get("/assistants/{assistant_id}/schemas", response_model=AgentSchemas)
async def get_assistant_schemas(assistant_id: str, user: User = Depends(get_current_user)):
    """Get input, output, state and config schemas for an assistant"""
    
    if assistant_id not in _assistants_db:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    assistant = _assistants_db[assistant_id]
    if assistant.user_id != user.identity:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    try:
        graph = await langgraph_service.get_graph(assistant.graph_id)
        
        # Extract schemas from LangGraph definition
        schemas = AgentSchemas(
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "User input message"}
                },
                "required": ["input"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "output": {"type": "string", "description": "Agent response"}
                }
            },
            state_schema={"type": "object", "additionalProperties": True},
            config_schema={
                "type": "object",
                "properties": {
                    "configurable": {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "user_id": {"type": "string"}
                        }
                    }
                }
            }
        )
        
        return schemas
        
    except Exception as e:
        raise HTTPException(400, f"Failed to extract schemas: {str(e)}")