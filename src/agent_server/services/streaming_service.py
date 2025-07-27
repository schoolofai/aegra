"""Streaming service for orchestrating SSE streaming - LangGraph Compatible"""
import asyncio
from typing import Dict, AsyncIterator, Optional, Any
from datetime import datetime

from ..models import Run, User
from ..core.sse import (
    create_metadata_event, create_values_event, 
    create_end_event, create_error_event, create_events_event,
    create_messages_event, create_state_event, create_logs_event,
    create_tasks_event, create_subgraphs_event, create_debug_event
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
        stream_mode: Optional[list[str]] = None
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
                
            async for event in self._stream_fresh_execution(run, user, config, stream_mode):
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
        stream_mode: list[str] = None
    ) -> AsyncIterator[str]:
        """Stream fresh execution from the beginning with LangGraph compatibility"""
        
        run_id = run.run_id
        stream_mode = stream_mode or ["values"]
        
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
            
            # Generic handler for mixed stream modes
            async for raw_event in graph.astream(
                run.input, config=run_config, stream_mode=stream_mode
            ):
                self.event_counters[run_id] += 1
                event_counter = self.event_counters[run_id]
                event_id = f"{run_id}_event_{event_counter}"

                # Determine the structure of the raw event
                node_path: str | None = None
                stream_mode_label: str | None = None
                event_payload: Any = None

                if isinstance(raw_event, tuple):
                    # Could be (stream_mode, event) OR (node_path, stream_mode, event)
                    if len(raw_event) == 2:
                        stream_mode_label, event_payload = raw_event
                    elif len(raw_event) == 3:
                        node_path, stream_mode_label, event_payload = raw_event
                    else:
                        # Unrecognized tuple format; skip
                        continue
                else:
                    # Non-tuple events correspond to 'values' mode when included alone
                    stream_mode_label = "values"
                    event_payload = raw_event

                # Handle each supported mode
                if stream_mode_label == "messages":
                    # event_payload is expected to be (message_chunk, metadata)
                    if isinstance(event_payload, tuple) and len(event_payload) == 2:
                        message_chunk, metadata = event_payload
                        messages_event = create_messages_event(
                            (message_chunk, metadata), event_id=event_id
                        )
                        await store_sse_event(
                            run_id,
                            event_id,
                            "messages",
                            {
                                "type": "messages_stream",
                                "message_chunk": message_chunk,
                                "metadata": metadata,
                                "node_path": node_path,
                            },
                        )
                        yield messages_event
                elif stream_mode_label == "values":
                    values_event = create_values_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "values",
                        {"type": "execution_values", "chunk": event_payload},
                    )
                    yield values_event
                elif stream_mode_label == "state":
                    state_event = create_state_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "state",
                        {"type": "state_stream", "state": event_payload},
                    )
                    yield state_event
                elif stream_mode_label == "logs":
                    logs_event = create_logs_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "logs",
                        {"type": "logs_stream", "logs": event_payload},
                    )
                    yield logs_event
                elif stream_mode_label == "tasks":
                    tasks_event = create_tasks_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "tasks",
                        {"type": "tasks_stream", "tasks": event_payload},
                    )
                    yield tasks_event
                elif stream_mode_label == "subgraphs":
                    subgraphs_event = create_subgraphs_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "subgraphs",
                        {"type": "subgraphs_stream", "subgraphs": event_payload},
                    )
                    yield subgraphs_event
                elif stream_mode_label == "events":
                    events_event = create_events_event(
                        {
                            "event": "on_chain_stream",
                            "run_id": run_id,
                            "data": event_payload,
                            "node_path": node_path,
                        },
                        event_id,
                    )
                    await store_sse_event(
                        run_id,
                        event_id,
                        "events",
                        {"type": "events_stream", "event": event_payload},
                    )
                    yield events_event
                elif stream_mode_label == "debug":
                    debug_event = create_debug_event(event_payload, event_id)
                    await store_sse_event(
                        run_id,
                        event_id,
                        "debug",
                        {"type": "debug_stream", "debug": event_payload},
                    )
                    yield debug_event

                # Update final output if event includes 'messages'
                if stream_mode_label == "values" and isinstance(event_payload, dict):
                    final_output = event_payload

            # End of astream loop
            # Note: final_output handling below remains unchanged
            if final_output is not None:
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