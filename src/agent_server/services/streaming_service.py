"""Streaming service for orchestrating SSE streaming"""
import asyncio
from typing import Dict, AsyncIterator, Optional, Any
from datetime import datetime

from ..models import Run, User
from ..core.sse import (
    create_start_event, create_chunk_event, create_complete_event,
    create_error_event, create_cancelled_event, create_interrupted_event
)
from .event_store import event_store, store_sse_event
from .langgraph_service import get_langgraph_service, create_run_config


class StreamingService:
    """Service to handle SSE streaming orchestration"""
    
    def __init__(self):
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.event_counters: Dict[str, int] = {}
    
    async def stream_run_execution(
        self, 
        run: Run, 
        user: User, 
        from_event_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream run execution with proper event handling"""
        
        run_id = run.run_id
        
        try:
            # Handle replay from specific event ID
            if from_event_id:
                async for replay_event in self._replay_events(run_id, from_event_id):
                    yield replay_event
                
                # Check if run is already completed
                if run.status in ["completed", "failed", "cancelled", "interrupted"]:
                    return
            
            # Initialize event counter
            if run_id not in self.event_counters:
                self.event_counters[run_id] = 0
            
            # Start fresh execution streaming
            async for event in self._stream_fresh_execution(run, user):
                yield event
                
        except asyncio.CancelledError:
            # Handle client disconnect or cancellation
            await self._handle_cancellation(run_id)
            raise
        except Exception as e:
            # Handle streaming errors
            await self._handle_error(run_id, str(e))
            raise
        finally:
            # Clean up
            self.active_streams.pop(run_id, None)
            self.event_counters.pop(run_id, None)
    
    async def _replay_events(self, run_id: str, from_event_id: str) -> AsyncIterator[str]:
        """Replay events from stored history"""
        missed_events = await event_store.get_events_since(run_id, from_event_id)
        
        for event in missed_events:
            yield event.format()
    
    async def _stream_fresh_execution(self, run: Run, user: User) -> AsyncIterator[str]:
        """Stream fresh execution from the beginning"""
        
        run_id = run.run_id
        
        # Update run status to streaming
        await self._update_run_status(run_id, "streaming")
        
        # Increment and send start event
        self.event_counters[run_id] += 1
        event_counter = self.event_counters[run_id]
        
        start_event = create_start_event(run_id, event_counter)
        await store_sse_event(
            run_id, 
            f"{run_id}_event_{event_counter}", 
            "start", 
            {"type": "run_start", "run_id": run_id, "status": "streaming"}
        )
        yield start_event
        
        try:
            # Get LangGraph service and load graph
            langgraph_service = get_langgraph_service()
            graph = await langgraph_service.get_graph(run.assistant_id)
            
            # Create run configuration with user context
            config = create_run_config(run_id, run.thread_id, user, run.config or {})
            
            # Stream graph execution
            async for chunk in graph.astream(run.input, config=config):
                self.event_counters[run_id] += 1
                event_counter = self.event_counters[run_id]
                
                chunk_event = create_chunk_event(run_id, event_counter, chunk)
                await store_sse_event(
                    run_id,
                    f"{run_id}_event_{event_counter}",
                    "chunk",
                    {"type": "execution_chunk", "chunk": chunk}
                )
                yield chunk_event
            
            # Get final state and send completion event
            final_state = graph.get_state(config)
            final_output = final_state.values if final_state else None
            
            self.event_counters[run_id] += 1
            event_counter = self.event_counters[run_id]
            
            complete_event = create_complete_event(run_id, event_counter, final_output)
            await store_sse_event(
                run_id,
                f"{run_id}_event_{event_counter}",
                "complete",
                {"type": "run_complete", "status": "completed", "final_output": final_output}
            )
            
            # Update run status
            await self._update_run_status(run_id, "completed", output=final_output)
            
            yield complete_event
            
        except asyncio.CancelledError:
            await self._handle_cancellation(run_id)
            raise
        except Exception as e:
            await self._handle_error(run_id, str(e))
            raise
    
    async def _handle_cancellation(self, run_id: str):
        """Handle run cancellation"""
        if run_id not in self.event_counters:
            self.event_counters[run_id] = 0
        
        self.event_counters[run_id] += 1
        event_counter = self.event_counters[run_id]
        
        cancel_event = create_cancelled_event(run_id, event_counter)
        await store_sse_event(
            run_id,
            f"{run_id}_event_{event_counter}",
            "cancelled",
            {"type": "run_cancelled", "status": "cancelled"}
        )
        
        await self._update_run_status(run_id, "cancelled")
    
    async def _handle_error(self, run_id: str, error: str):
        """Handle execution errors"""
        if run_id not in self.event_counters:
            self.event_counters[run_id] = 0
        
        self.event_counters[run_id] += 1
        event_counter = self.event_counters[run_id]
        
        error_event = create_error_event(run_id, event_counter, error)
        await store_sse_event(
            run_id,
            f"{run_id}_event_{event_counter}",
            "error",
            {"type": "execution_error", "error": error, "status": "failed"}
        )
        
        await self._update_run_status(run_id, "failed", error=error)
    
    async def interrupt_run(self, run_id: str) -> bool:
        """Interrupt a running execution"""
        if run_id in self.active_streams:
            task = self.active_streams[run_id]
            if not task.done():
                task.cancel()
                
                # Send interruption event
                if run_id not in self.event_counters:
                    self.event_counters[run_id] = 0
                
                self.event_counters[run_id] += 1
                event_counter = self.event_counters[run_id]
                
                interrupt_event = create_interrupted_event(run_id, event_counter)
                await store_sse_event(
                    run_id,
                    f"{run_id}_event_{event_counter}",
                    "interrupted",
                    {"type": "run_interrupted", "status": "interrupted"}
                )
                
                await self._update_run_status(run_id, "interrupted")
                return True
        
        return False
    
    async def cancel_run(self, run_id: str) -> bool:
        """Cancel a pending or running execution"""
        if run_id in self.active_streams:
            task = self.active_streams[run_id]
            if not task.done():
                task.cancel()
                await self._handle_cancellation(run_id)
                return True
        
        # If not actively streaming, just update status
        await self._update_run_status(run_id, "cancelled")
        return True
    
    async def _update_run_status(self, run_id: str, status: str, output: Any = None, error: str = None):
        """Update run status in database"""
        # Import here to avoid circular imports
        from ..api.runs import _runs_db, update_run_status
        
        if run_id in _runs_db:
            await update_run_status(run_id, status, output, error)
    
    def is_run_streaming(self, run_id: str) -> bool:
        """Check if run is currently streaming"""
        task = self.active_streams.get(run_id)
        return task is not None and not task.done()
    
    async def cleanup_run(self, run_id: str):
        """Clean up streaming resources for a run"""
        self.active_streams.pop(run_id, None)
        self.event_counters.pop(run_id, None)
        await event_store.cleanup_events(run_id)


# Global streaming service instance
streaming_service = StreamingService()