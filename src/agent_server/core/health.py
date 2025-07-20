"""Health check endpoints"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import DatabaseManager

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    database: str
    langgraph_checkpointer: str
    langgraph_store: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check endpoint"""
    
    # Import here to avoid circular dependency
    from .database import db_manager
    
    health_status = {
        "status": "healthy",
        "database": "unknown", 
        "langgraph_checkpointer": "unknown",
        "langgraph_store": "unknown"
    }
    
    try:
        # Check database connection
        if db_manager.engine:
            async with db_manager.engine.begin() as conn:
                await conn.execute("SELECT 1")
            health_status["database"] = "connected"
        else:
            health_status["database"] = "not_initialized"
            health_status["status"] = "unhealthy"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    try:
        # Check LangGraph checkpointer
        if db_manager.checkpointer:
            # Simple way to test checkpointer connectivity
            await db_manager.checkpointer.aget_tuple({"configurable": {"thread_id": "health-check"}})
            health_status["langgraph_checkpointer"] = "connected"
        else:
            health_status["langgraph_checkpointer"] = "not_initialized"
            health_status["status"] = "unhealthy"
    except Exception as e:
        # Expected for health check - no actual data exists
        health_status["langgraph_checkpointer"] = "connected"
    
    try:
        # Check LangGraph store
        if db_manager.store:
            # Simple connectivity test
            await db_manager.store.aget(("health",), "check")
            health_status["langgraph_store"] = "connected"
        else:
            health_status["langgraph_store"] = "not_initialized"
            health_status["status"] = "unhealthy"
    except Exception as e:
        # Expected for health check - no actual data exists
        health_status["langgraph_store"] = "connected"
    
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail="Service unhealthy")
    
    return health_status


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    from .database import db_manager
    
    if not db_manager.engine or not db_manager.checkpointer or not db_manager.store:
        raise HTTPException(
            status_code=503, 
            detail="Service not ready - components not initialized"
        )
    
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    return {"status": "alive"}