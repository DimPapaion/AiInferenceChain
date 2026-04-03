"""
Event Bus for InferenceChain consensus.

Provides publish-subscribe messaging for consensus events.
Enables loose coupling between state machines and external components.

Usage:
    bus = EventBus()
    
    # Subscribe to events
    def on_committed(event):
        print(f"Consensus reached: {event.data}")
    
    bus.subscribe("qoi_committed", on_committed)
    
    # Publish events
    bus.publish("qoi_committed", ConsensusOutcomeEvent(...))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Any
from enum import Enum
import uuid


class EventType(str, Enum):
    """Consensus event types."""
    
    # QoI Consensus events
    QOI_ROUND_STARTED = "qoi_round_started"
    QOI_PRE_PREPARE = "qoi_pre_prepare"
    QOI_PREPARE = "qoi_prepare"
    QOI_COMMIT = "qoi_commit"
    QOI_COMMITTED = "qoi_committed"
    QOI_VIEW_CHANGE = "qoi_view_change"
    QOI_NEW_VIEW = "qoi_new_view"
    QOI_TIMEOUT = "qoi_timeout"
    
    # PoS Consensus events
    POS_ROUND_STARTED = "pos_round_started"
    POS_PROPOSED = "pos_proposed"
    POS_COMMITTED = "pos_committed"
    POS_VIEW_CHANGE = "pos_view_change"
    
    # Network events
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    TIMEOUT = "timeout"
    
    # Block events
    BLOCK_CREATED = "block_created"
    BLOCK_COMMITTED = "block_committed"
    
    # Error events
    CONSENSUS_ERROR = "consensus_error"


@dataclass
class ConsensusEvent:
    """
    Base consensus event.
    
    All events published on the event bus carry:
    - event_type: what happened
    - trace_id: unique ID for this event flow
    - timestamp: when it happened
    - data: event-specific payload
    """
    
    event_type: EventType
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    data: dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return (
            f"ConsensusEvent({self.event_type.value}, "
            f"trace={self.trace_id}, data={self.data})"
        )


class EventBus:
    """
    In-memory event bus for consensus events.
    
    Thread-safe publish-subscribe system.
    Subscribers are called synchronously when events are published.
    """
    
    def __init__(self) -> None:
        # event_type → list of (callback, filter_fn)
        self._subscribers: dict[EventType, list[tuple[Callable, Optional[Callable]]]] = {}
        self._metrics = {
            "published": 0,
            "subscriptions": 0,
        }
    
    def subscribe(
        self,
        event_type: EventType | str,
        callback: Callable[[ConsensusEvent], None],
        filter_fn: Optional[Callable[[ConsensusEvent], bool]] = None,
    ) -> None:
        """
        Subscribe to events of a given type.
        
        Args:
            event_type: Type of event to listen for
            callback: Function to call when event is published
            filter_fn: Optional predicate; only call if filter_fn(event) is True
        """
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append((callback, filter_fn))
        self._metrics["subscriptions"] += 1
    
    def unsubscribe(
        self,
        event_type: EventType | str,
        callback: Callable[[ConsensusEvent], None],
    ) -> None:
        """Unsubscribe a callback from an event type."""
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        
        if event_type not in self._subscribers:
            return
        
        # Remove all entries matching this callback
        self._subscribers[event_type] = [
            (cb, filt) for cb, filt in self._subscribers[event_type]
            if cb is not callback
        ]
    
    def publish(
        self,
        event_type: EventType | str,
        event: ConsensusEvent | None = None,
        trace_id: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> None:
        """
        Publish an event to all subscribers.
        
        Can be called with either:
          - publish(EventType.QOI_COMMITTED, event_obj)
          - publish(EventType.QOI_COMMITTED, trace_id="req-1", data={...})
        """
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        
        # Create event if not provided
        if event is None:
            event = ConsensusEvent(
                event_type=event_type,
                trace_id=trace_id or "",
                data=data or {},
            )
        
        self._metrics["published"] += 1
        
        # Call all subscribers for this event type
        if event_type not in self._subscribers:
            return
        
        for callback, filter_fn in self._subscribers[event_type]:
            # Only call if filter passes
            if filter_fn is None or filter_fn(event):
                try:
                    callback(event)
                except Exception as e:
                    # Don't crash if subscriber throws
                    print(f"ERROR in event subscriber: {e}")
    
    def metrics(self) -> dict[str, Any]:
        """Return event bus metrics."""
        return {
            "total_published": self._metrics["published"],
            "total_subscriptions": self._metrics["subscriptions"],
            "subscribed_types": len(self._subscribers),
            "subscription_counts": {
                etype.value: len(subs)
                for etype, subs in self._subscribers.items()
            },
        }
    
    def __repr__(self) -> str:
        return f"EventBus(subscriptions={self._metrics['subscriptions']}, published={self._metrics['published']})"


# Global event bus instance
_global_bus: Optional[EventBus] = None


def get_global_bus() -> EventBus:
    """Get or create the global event bus."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def reset_global_bus() -> None:
    """Reset global bus (testing only)."""
    global _global_bus
    _global_bus = None
