"""Event store for SSE replay functionality"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from ..core.sse import SSEEvent


class EventStore:
    """In-memory event store for SSE replay functionality"""
    
    # Maximum events to store per run (prevent memory leaks)
    MAX_EVENTS_PER_RUN = 1000
    
    # Event cleanup interval in seconds
    CLEANUP_INTERVAL = 300  # 5 minutes
    
    def __init__(self):
        self.events: Dict[str, List[SSEEvent]] = {}
        self.run_timestamps: Dict[str, datetime] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def start_cleanup_task(self):
        """Start background cleanup task"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop_cleanup_task(self):
        """Stop background cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def store_event(self, run_id: str, event: SSEEvent):
        """Store event for potential replay"""
        async with self._lock:
            if run_id not in self.events:
                self.events[run_id] = []
                self.run_timestamps[run_id] = datetime.utcnow()
            
            self.events[run_id].append(event)
            
            # Limit event history per run
            if len(self.events[run_id]) > self.MAX_EVENTS_PER_RUN:
                self.events[run_id] = self.events[run_id][-self.MAX_EVENTS_PER_RUN:]
    
    async def get_events_since(self, run_id: str, last_event_id: str) -> List[SSEEvent]:
        """Get events that occurred after last_event_id"""
        async with self._lock:
            events = self.events.get(run_id, [])
            
            if not events:
                return []
            
            # Find the last event index by exact ID match first
            last_index = -1
            for i, event in enumerate(events):
                if event.id == last_event_id:
                    last_index = i
                    break
            
            # If exact match not found, try sequence-based lookup for mock IDs
            if last_index == -1:
                try:
                    # Extract sequence number from the provided event_id (e.g., mock_event_8 -> 8)
                    target_sequence = int(last_event_id.split("_event_")[-1])
                    
                    # Find the last stored event with sequence <= target_sequence
                    for i, event in enumerate(events):
                        try:
                            event_sequence = int(event.id.split("_event_")[-1])
                            if event_sequence == target_sequence:
                                last_index = i
                                break
                        except (ValueError, IndexError):
                            continue
                except (ValueError, IndexError):
                    # If we can't parse the sequence, return all events (fallback behavior)
                    pass
            
            # Return events after the last received event
            return events[last_index + 1:] if last_index >= 0 else events
    
    async def get_all_events(self, run_id: str) -> List[SSEEvent]:
        """Get all events for a run"""
        async with self._lock:
            return self.events.get(run_id, []).copy()
    
    async def cleanup_events(self, run_id: str):
        """Clean up events after run completion"""
        async with self._lock:
            self.events.pop(run_id, None)
            self.run_timestamps.pop(run_id, None)
    
    async def get_run_info(self, run_id: str) -> Optional[Dict]:
        """Get basic run info from stored events"""
        async with self._lock:
            events = self.events.get(run_id, [])
            if not events:
                return None
            
            first_event = events[0]
            last_event = events[-1]
            
            return {
                "run_id": run_id,
                "event_count": len(events),
                "first_event_time": first_event.timestamp,
                "last_event_time": last_event.timestamp,
                "last_event_id": last_event.id
            }
    
    async def _cleanup_loop(self):
        """Background cleanup of old events"""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_old_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in event store cleanup: {e}")
    
    async def _cleanup_old_runs(self):
        """Clean up events for runs older than 1 hour"""
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        
        async with self._lock:
            runs_to_cleanup = [
                run_id for run_id, timestamp in self.run_timestamps.items()
                if timestamp < cutoff_time
            ]
            
            for run_id in runs_to_cleanup:
                self.events.pop(run_id, None)
                self.run_timestamps.pop(run_id, None)
            
            if runs_to_cleanup:
                print(f"Cleaned up events for {len(runs_to_cleanup)} old runs")


# Global event store instance
event_store = EventStore()


async def store_sse_event(run_id: str, event_id: str, event_type: str, data: Dict):
    """Helper function to store SSE event"""
    event = SSEEvent(
        id=event_id,
        event=event_type,
        data=data,
        timestamp=datetime.utcnow()
    )
    await event_store.store_event(run_id, event)
    return event