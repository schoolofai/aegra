"""Server-Sent Events utilities and formatting"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SSEEvent:
    """Server-Sent Event data structure"""
    id: str
    event: str
    data: Dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def format(self) -> str:
        """Format as proper SSE event"""
        json_data = json.dumps(self.data, default=str)
        return f"id: {self.id}\nevent: {self.event}\ndata: {json_data}\n\n"


def format_sse_event(id: str, event: str, data: Dict[str, Any]) -> str:
    """Format data as Server-Sent Event"""
    json_data = json.dumps(data, default=str)
    return f"id: {id}\nevent: {event}\ndata: {json_data}\n\n"


def create_start_event(run_id: str, event_counter: int) -> str:
    """Create streaming start event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="start",
        data={
            "type": "run_start",
            "run_id": run_id,
            "status": "streaming",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_chunk_event(run_id: str, event_counter: int, chunk_data: Dict[str, Any]) -> str:
    """Create streaming chunk event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="chunk",
        data={
            "type": "execution_chunk",
            "run_id": run_id,
            "chunk": chunk_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_complete_event(run_id: str, event_counter: int, final_output: Any = None) -> str:
    """Create streaming completion event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="complete",
        data={
            "type": "run_complete",
            "run_id": run_id,
            "status": "completed",
            "final_output": final_output,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_error_event(run_id: str, event_counter: int, error: str, error_type: str = "execution_error") -> str:
    """Create streaming error event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="error",
        data={
            "type": error_type,
            "run_id": run_id,
            "status": "failed",
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_cancelled_event(run_id: str, event_counter: int) -> str:
    """Create streaming cancellation event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="cancelled",
        data={
            "type": "run_cancelled",
            "run_id": run_id,
            "status": "cancelled",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def create_interrupted_event(run_id: str, event_counter: int) -> str:
    """Create streaming interruption event"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="interrupted",
        data={
            "type": "run_interrupted",
            "run_id": run_id,
            "status": "interrupted",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def get_sse_headers() -> Dict[str, str]:
    """Get standard SSE response headers"""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable nginx buffering
        "Content-Type": "text/event-stream"
    }