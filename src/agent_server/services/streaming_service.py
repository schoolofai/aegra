"""Streaming service for orchestrating SSE streaming - LangGraph Compatible"""
import asyncio
from typing import Dict, AsyncIterator, Optional, Any
from datetime import datetime

from ..models import Run, User
from ..core.sse import (
    create_metadata_event, create_values_event, create_debug_event, 
    create_end_event, create_error_event, create_events_event
)
from .event_store import event_store, store_sse_event
from .langgraph_service import get_langgraph_service, create_run_config


class StreamingService:
    """Service to handle SSE streaming orchestration with LangGraph compatibility"""
    
    def __init__(self):
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.event_counters: Dict[str, int] = {}
    
    async def stream_run_execution(
        self, 
        run: Run, 
        user: User, 
        from_event_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        stream_mode: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream run execution with proper LangGraph event handling"""
        
        run_id = run.run_id
        
        try:
            # Handle replay from specific event ID (if supported)
            if from_event_id:
                async for replay_event in self._replay_events(run_id, from_event_id):
                    yield replay_event
                
                # Check if run is already completed
                if run.status in ["completed", "failed", "cancelled", "interrupted"]:
                    return
            
            # Initialize event counter
            if run_id not in self.event_counters:
                self.event_counters[run_id] = 0
            
            # Parse stream mode - default to "values" like LangGraph
            if not stream_mode:
                stream_modes = ["values"]
            elif isinstance(stream_mode, str):
                stream_modes = [mode.strip() for mode in stream_mode.split(",")]
            else:
                stream_modes = ["values"]
            
            # Start fresh execution streaming
            async for event in self._stream_fresh_execution(run, user, config, stream_modes):
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
        """Replay events from stored history - convert legacy format to new format"""
        missed_events = await event_store.get_events_since(run_id, from_event_id)
        
        for event in missed_events:
            # Convert legacy events to new SSE format
            if event.event == "start":
                yield create_metadata_event(run_id, event.id)
            elif event.event == "chunk":
                yield create_values_event(event.data.get("chunk", {}), event.id)
            elif event.event == "complete":
                yield create_end_event(event.id)
    
    async def _stream_fresh_execution(
        self, 
        run: Run, 
        user: User, 
        config: Optional[Dict[str, Any]] = None,
        stream_modes: list[str] = None
    ) -> AsyncIterator[str]:
        """Stream fresh execution from the beginning with LangGraph compatibility"""
        
        run_id = run.run_id
        stream_modes = stream_modes or ["values"]
        
        # Update run status to streaming
        await self._update_run_status(run_id, "streaming")
        
        # Increment and send metadata event (equivalent to LangGraph's metadata event)
        self.event_counters[run_id] += 1
        event_counter = self.event_counters[run_id]
        event_id = f"{run_id}_event_{event_counter}"
        
        metadata_event = create_metadata_event(run_id, event_id)
        await store_sse_event(
            run_id, 
            event_id, 
            "metadata", 
            {"type": "run_metadata", "run_id": run_id, "status": "streaming"}
        )
        yield metadata_event
        
        try:
            # Get LangGraph service and load graph
            langgraph_service = get_langgraph_service()
            
            # Get assistant to find the correct graph_id
            from ..api.assistants import _assistants_db
            assistant = _assistants_db[run.assistant_id]
            
            # Load graph using the assistant's graph_id
            graph = await langgraph_service.get_graph(assistant.graph_id)
            
            # Create run configuration with user context
            run_config = create_run_config(run_id, run.thread_id, user, config or {})
            
            # Stream graph execution and collect outputs by mode
            final_output = None
            debug_info = []
            
            # Use the graph's astream method which is what LangGraph expects
            async for chunk in graph.astream(run.input, config=run_config):
                self.event_counters[run_id] += 1
                event_counter = self.event_counters[run_id]
                event_id = f"{run_id}_event_{event_counter}"
                
                # Keep track of the last chunk as final output
                final_output = chunk
                
                # Send events based on requested stream modes
                if "values" in stream_modes:
                    values_event = create_values_event(chunk, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "values",
                        {"type": "execution_values", "chunk": chunk}
                    )
                    yield values_event
                
                # If debug mode is requested, we'd add debug events here
                if "debug" in stream_modes:
                    debug_data = {
                        "step": event_counter,
                        "timestamp": datetime.utcnow().isoformat(),
                        "chunk_type": type(chunk).__name__
                    }
                    debug_event = create_debug_event(debug_data, event_id)
                    yield debug_event
                
                # If events mode is requested, send the raw chunk as an event
                if "events" in stream_modes:
                    event_data = {
                        "event": "on_chain_stream",
                        "run_id": run_id,
                        "data": {"chunk": chunk}
                    }
                    events_event = create_events_event(event_data, event_id)
                    yield events_event
            
            # Send final end event
            self.event_counters[run_id] += 1
            event_counter = self.event_counters[run_id]
            event_id = f"{run_id}_event_{event_counter}"
            
            end_event = create_end_event(event_id)
            await store_sse_event(
                run_id,
                event_id,
                "end",
                {"type": "run_complete", "status": "completed", "final_output": final_output}
            )
            
            # Update run status
            await self._update_run_status(run_id, "completed", output=final_output)
            
            yield end_event
            
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
        event_id = f"{run_id}_event_{event_counter}"
        
        # Send error event for cancellation
        error_event = create_error_event("Run was cancelled", event_id)
        await store_sse_event(
            run_id,
            event_id,
            "error",
            {"type": "run_cancelled", "status": "cancelled"}
        )
        
        await self._update_run_status(run_id, "cancelled")
    
    async def _handle_error(self, run_id: str, error: str):
        """Handle execution errors"""
        if run_id not in self.event_counters:
            self.event_counters[run_id] = 0
        
        self.event_counters[run_id] += 1
        event_counter = self.event_counters[run_id]
        event_id = f"{run_id}_event_{event_counter}"
        
        error_event = create_error_event(error, event_id)
        await store_sse_event(
            run_id,
            event_id,
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
                
                # Send interruption error event
                if run_id not in self.event_counters:
                    self.event_counters[run_id] = 0
                
                self.event_counters[run_id] += 1
                event_counter = self.event_counters[run_id]
                event_id = f"{run_id}_event_{event_counter}"
                
                error_event = create_error_event("Run was interrupted", event_id)
                await store_sse_event(
                    run_id,
                    event_id,
                    "error",
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