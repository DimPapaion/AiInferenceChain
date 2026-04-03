"""
Message scheduler for async consensus event delivery with delays.

Enables:
- Scheduling consensus events for delayed delivery
- Testing timeouts without real network delays
- Simulating network latency
- Coordinating multi-round consensus
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional, Any
from uuid import uuid4

from core.events import ConsensusEvent, EventType
from core.utils.logger import get_logger


@dataclass
class ScheduledMessage:
    """A message scheduled for future delivery."""
    
    message_id: str = field(default_factory=lambda: str(uuid4())[:8])
    event: ConsensusEvent = field(default=None)
    handler: Callable = field(default=None)  # Async function to call
    delay_secs: float = field(default=0.0)
    scheduled_at: datetime = field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = field(default=None)
    
    @property
    def delivery_time(self) -> datetime:
        """When this message should be delivered."""
        return self.scheduled_at + timedelta(seconds=self.delay_secs)
    
    @property
    def is_delivered(self) -> bool:
        """True if message has been delivered."""
        return self.delivered_at is not None


class MessageScheduler:
    """
    Schedule consensus event delivery with optional delays.
    
    Usage:
        scheduler = MessageScheduler()
        
        # Schedule message for delivery in 5 seconds
        await scheduler.schedule_deliver(
            delay_secs=5.0,
            event=my_event,
            handler=lambda e: await node.handle_message(e),
        )
        
        # All scheduled messages auto-deliver when ready
        await scheduler.run()  # Run in background
    """
    
    def __init__(self, background: bool = False):
        """
        Initialize message scheduler.
        
        Args:
            background: If True, start background delivery task automatically
        """
        self.logger = get_logger("message_scheduler")
        self._scheduled: dict[str, ScheduledMessage] = {}
        self._background_task: Optional[asyncio.Task] = None
        self._running = False
        
        if background:
            # Task is started lazily on first schedule_deliver
            pass
    
    async def schedule_deliver(
        self,
        event: ConsensusEvent,
        handler: Callable,
        delay_secs: float = 0.0,
    ) -> str:
        """
        Schedule a message for delivery.
        
        Args:
            event: ConsensusEvent to deliver
            handler: Async function to call with event (e.g., node.handle_message)
            delay_secs: Seconds to delay before delivery
            
        Returns:
            Message ID for tracking
        """
        msg = ScheduledMessage(
            event=event,
            handler=handler,
            delay_secs=delay_secs,
        )
        
        self._scheduled[msg.message_id] = msg
        
        self.logger.debug(
            "Message scheduled",
            trace_id=event.trace_id,
            context={
                "msg_id": msg.message_id,
                "delay_secs": delay_secs,
                "event_type": event.event_type.value,
            },
        )
        
        # Start background task if not running
        if not self._running:
            await self.start_background()
        
        return msg.message_id
    
    async def start_background(self) -> None:
        """Start background delivery task."""
        if self._running:
            return
        
        self._running = True
        self._background_task = asyncio.create_task(self._delivery_loop())
        self.logger.info("Message scheduler started background loop")
    
    async def _delivery_loop(self) -> None:
        """Background loop that delivers messages when ready."""
        while self._running:
            now = datetime.utcnow()
            
            for msg_id, msg in list(self._scheduled.items()):
                if msg.is_delivered:
                    continue
                
                if now >= msg.delivery_time:
                    # Deliver this message
                    try:
                        await self._deliver_message(msg)
                        msg.delivered_at = datetime.utcnow()
                        del self._scheduled[msg_id]
                    except Exception as e:
                        self.logger.error(
                            "Failed to deliver message",
                            trace_id=msg.event.trace_id,
                            context={"error": str(e), "msg_id": msg_id},
                        )
            
            # Check again in 10ms
            await asyncio.sleep(0.01)
    
    async def _deliver_message(self, msg: ScheduledMessage) -> None:
        """Deliver a single message."""
        import inspect
        try:
            if inspect.iscoroutinefunction(msg.handler):
                await msg.handler(msg.event)
            else:
                # Sync handler - call directly
                msg.handler(msg.event)
            
            self.logger.debug(
                "Message delivered",
                trace_id=msg.event.trace_id,
                context={
                    "msg_id": msg.message_id,
                    "delay_secs": msg.delay_secs,
                    "event_type": msg.event.event_type.value,
                },
            )
        except Exception as e:
            self.logger.error(
                "Failed to deliver message",
                trace_id=msg.event.trace_id,
                context={"error": str(e), "msg_id": msg.message_id},
            )
            raise
    
    async def wait_until_empty(self, timeout_secs: float = 30.0) -> bool:
        """
        Wait until all scheduled messages are delivered.
        
        Args:
            timeout_secs: Max seconds to wait
            
        Returns:
            True if all delivered, False if timeout
        """
        try:
            await asyncio.wait_for(
                self._wait_until_empty_impl(),
                timeout=timeout_secs,
            )
            return True
        except asyncio.TimeoutError:
            return False
    
    async def _wait_until_empty_impl(self) -> None:
        """Implementation of wait_until_empty."""
        while self._scheduled:
            await asyncio.sleep(0.01)
    
    async def stop(self) -> None:
        """Stop background delivery task."""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
    
    def get_scheduled_count(self) -> int:
        """Get number of scheduled (not yet delivered) messages."""
        return len(self._scheduled)
    
    def get_scheduled(self) -> dict[str, ScheduledMessage]:
        """Get all scheduled messages."""
        return dict(self._scheduled)
    
    def __repr__(self) -> str:
        return f"MessageScheduler(scheduled={len(self._scheduled)})"
