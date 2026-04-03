"""
View change orchestration for consensus recovery.

Handles primary rotation when the current primary times out or
becomes unavailable.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from core.events import ConsensusEvent, EventBus, EventType
from core.utils.logger import get_logger


@dataclass
class ViewChangeState:
    """State of a view change operation."""
    
    round_id: str
    old_view: int
    new_view: int
    started_at: datetime = field(default_factory=datetime.utcnow)
    view_change_votes: dict[str, bool] = field(default_factory=dict)
    new_view_msgs: dict[str, bool] = field(default_factory=dict)
    completed: bool = False
    
    def votes_needed(self, total_replicas: int) -> int:
        """Minimum votes needed for view change (2f+1)."""
        f = (total_replicas - 1) // 3
        return 2 * f + 1


class ViewChanger:
    """
    Orchestrate view changes on primary timeout.
    
    When the primary replica becomes unresponsive (timeout detected),
    non-primary replicas initiate a view change to elect a new primary.
    
    Usage:
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        # On timeout
        await changer.initiate_view_change(
            round_id="req-1",
            old_view=0,
            event_bus=bus,
        )
    """
    
    def __init__(
        self,
        node_id: str,
        total_replicas: int = 4,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize view changer.
        
        Args:
            node_id: This replica's ID
            total_replicas: Total replicas in cluster
            event_bus: Optional EventBus for publishing view change events
        """
        self.node_id = node_id
        self.total_replicas = total_replicas
        self.event_bus = event_bus
        self.logger = get_logger("view_changer")
        
        self._view_changes: dict[str, ViewChangeState] = {}
        self._on_view_changed: Optional[Callable[[str, int], None]] = None
    
    def set_view_changed_callback(
        self,
        callback: Callable[[str, int], None],
    ) -> None:
        """
        Set callback invoked when view change completes.
        
        Args:
            callback: Function(round_id, new_view)
        """
        self._on_view_changed = callback
    
    async def initiate_view_change(
        self,
        round_id: str,
        old_view: int,
        event_bus: Optional[EventBus] = None,
    ) -> bool:
        """
        Initiate view change for a stalled round.
        
        Args:
            round_id: Request ID of stalled round
            old_view: Current view number
            event_bus: EventBus for publishing (uses member if not provided)
            
        Returns:
            True if view change initiated successfully
        """
        if round_id in self._view_changes:
            self.logger.warn(
                "View change already in progress",
                context={"round_id": round_id, "view": old_view},
            )
            return False
        
        new_view = old_view + 1
        state = ViewChangeState(
            round_id=round_id,
            old_view=old_view,
            new_view=new_view,
        )
        
        self._view_changes[round_id] = state
        
        self.logger.info(
            "View change initiated",
            context={
                "round_id": round_id,
                "old_view": old_view,
                "new_view": new_view,
            },
        )
        
        # Publish VIEW_CHANGE event
        event = ConsensusEvent(
            event_type=EventType.QOI_VIEW_CHANGE,
            trace_id=round_id,
            data={
                "node_id": self.node_id,
                "round_id": round_id,
                "new_view": new_view,
            },
        )
        
        bus = event_bus or self.event_bus
        if bus:
            bus.publish(EventType.QOI_VIEW_CHANGE.value, event)
        
        # Wait for view change to complete
        await self._wait_for_view_change(round_id, new_view)
        
        return True
    
    async def handle_view_change_msg(
        self,
        event: ConsensusEvent,
    ) -> None:
        """
        Handle VIEW_CHANGE message from another replica.
        
        Args:
            event: ConsensusEvent with VIEW_CHANGE type
        """
        round_id = event.data.get("round_id")
        node_id = event.data.get("node_id")
        new_view = event.data.get("new_view")
        
        if not round_id or new_view is None:
            return
        
        # Create view change state if needed
        if round_id not in self._view_changes:
            state = ViewChangeState(
                round_id=round_id,
                old_view=new_view - 1,
                new_view=new_view,
            )
            self._view_changes[round_id] = state
        
        state = self._view_changes[round_id]
        
        # Count votes
        if node_id:
            state.view_change_votes[node_id] = True
        
        votes_needed = state.votes_needed(self.total_replicas)
        current_votes = len(state.view_change_votes)
        
        self.logger.debug(
            "VIEW_CHANGE vote received",
            trace_id=round_id,
            context={
                "from_node": node_id,
                "new_view": new_view,
                "votes": f"{current_votes}/{votes_needed}",
            },
        )
        
        # Check if view change can be finalized
        if current_votes >= votes_needed and not state.completed:
            state.completed = True
            
            self.logger.info(
                "View change consensus reached",
                trace_id=round_id,
                context={
                    "new_view": new_view,
                    "votes": current_votes,
                },
            )
            
            # Publish NEW_VIEW event
            event = ConsensusEvent(
                event_type=EventType.QOI_NEW_VIEW,
                trace_id=round_id,
                data={
                    "round_id": round_id,
                    "new_view": new_view,
                },
            )
            
            if self.event_bus:
                self.event_bus.publish(EventType.QOI_NEW_VIEW.value, event)
            
            # Invoke callback
            if self._on_view_changed:
                import inspect
                if inspect.iscoroutinefunction(self._on_view_changed):
                    await self._on_view_changed(round_id, new_view)
                else:
                    self._on_view_changed(round_id, new_view)
    
    async def _wait_for_view_change(
        self,
        round_id: str,
        new_view: int,
        timeout_secs: float = 10.0,
    ) -> None:
        """
        Wait for view change to complete.
        
        Args:
            round_id: Request ID
            new_view: Target view number
            timeout_secs: Max time to wait
        """
        state = self._view_changes[round_id]
        start = asyncio.get_event_loop().time()
        
        while not state.completed:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout_secs:
                self.logger.error(
                    "View change timeout",
                    trace_id=round_id,
                    context={"timeout_secs": timeout_secs},
                )
                break
            
            await asyncio.sleep(0.1)
    
    def get_view_change_state(
        self,
        round_id: str,
    ) -> Optional[ViewChangeState]:
        """Get view change state for round."""
        return self._view_changes.get(round_id)
    
    def clear_view_change(self, round_id: str) -> None:
        """Clear view change state (after consensus reached)."""
        if round_id in self._view_changes:
            del self._view_changes[round_id]
            
            self.logger.debug(
                "View change cleared",
                context={"round_id": round_id},
            )
    
    def __repr__(self) -> str:
        return f"ViewChanger(node_id={self.node_id}, active_changes={len(self._view_changes)})"
