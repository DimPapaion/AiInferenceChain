"""
Timeout manager for detecting stalled consensus rounds.

Tracks active consensus rounds and detects when they timeout,
triggering view changes for recovery.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
from uuid import uuid4

from core.utils.logger import get_logger


@dataclass
class ActiveRound:
    """A consensus round being tracked for timeout."""
    
    round_id: str
    view: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    timeout_secs: float = 30.0
    
    @property
    def timeout_at(self) -> datetime:
        """When this round times out."""
        return self.started_at + timedelta(seconds=self.timeout_secs)
    
    @property
    def elapsed_secs(self) -> float:
        """Seconds elapsed since round started."""
        return (datetime.utcnow() - self.started_at).total_seconds()
    
    @property
    def is_timed_out(self) -> bool:
        """True if this round has timed out."""
        return datetime.utcnow() >= self.timeout_at
    
    @property
    def time_until_timeout_secs(self) -> float:
        """Seconds until timeout (negative if already timed out)."""
        return (self.timeout_at - datetime.utcnow()).total_seconds()


class TimeoutManager:
    """
    Track consensus rounds and detect timeouts.
    
    Usage:
        tm = TimeoutManager(timeout_secs=30)
        
        # Start tracking a round
        tm.start_round("req-1")
        
        # Check for timeouts periodically
        timed_out = await tm.check_timeouts()
        for round_id in timed_out:
            await trigger_view_change(round_id)
    """
    
    def __init__(
        self,
        timeout_secs: float = 30.0,
        on_timeout: Optional[Callable[[str, int], None]] = None,
    ):
        """
        Initialize timeout manager.
        
        Args:
            timeout_secs: Seconds before a round times out
            on_timeout: Optional callback(round_id, view) when timeout fires
        """
        self.timeout_secs = timeout_secs
        self.on_timeout = on_timeout
        self.logger = get_logger("timeout_manager")
        
        self._active_rounds: dict[str, ActiveRound] = {}
        self._check_task: Optional[asyncio.Task] = None
        self._background_running = False
    
    def start_round(self, round_id: str, view: int = 0) -> None:
        """
        Start tracking a round.
        
        Args:
            round_id: Request ID for this round
            view: Current view number (for tracking primary changes)
        """
        if round_id in self._active_rounds:
            self.logger.warn(
                "Round already tracked",
                context={"round_id": round_id},
            )
            return
        
        self._active_rounds[round_id] = ActiveRound(
            round_id=round_id,
            view=view,
            timeout_secs=self.timeout_secs,
        )
        
        self.logger.debug(
            "Round tracking started",
            context={"round_id": round_id, "timeout_secs": self.timeout_secs},
        )
    
    def end_round(self, round_id: str) -> None:
        """
        Stop tracking a round (consensus reached).
        
        Args:
            round_id: Request ID to stop tracking
        """
        if round_id in self._active_rounds:
            del self._active_rounds[round_id]
            self.logger.debug(
                "Round tracking ended",
                context={"round_id": round_id},
            )
    
    def update_view(self, round_id: str, new_view: int) -> None:
        """
        Update view number for a tracked round.
        
        Args:
            round_id: Request ID
            new_view: New view number
        """
        if round_id in self._active_rounds:
            self._active_rounds[round_id].view = new_view
    
    async def check_timeouts(self) -> list[tuple[str, int]]:
        """
        Check for timed out rounds.
        
        Returns:
            List of (round_id, view) tuples that have timed out
        """
        timed_out = []
        
        for round_id, round_info in list(self._active_rounds.items()):
            if round_info.is_timed_out:
                timed_out.append((round_id, round_info.view))
                
                self.logger.warn(
                    "Round timeout detected",
                    context={
                        "round_id": round_id,
                        "view": round_info.view,
                        "elapsed_secs": round_info.elapsed_secs,
                    },
                )
                
                # Call timeout callback if provided
                if self.on_timeout:
                    import inspect
                    try:
                        if inspect.iscoroutinefunction(self.on_timeout):
                            await self.on_timeout(round_id, round_info.view)
                        else:
                            self.on_timeout(round_id, round_info.view)
                    except Exception as e:
                        self.logger.error(
                            "Error invoking timeout callback",
                            context={"error": str(e), "round_id": round_id},
                        )
                
                # Stop tracking (will restart with new view)
                del self._active_rounds[round_id]
        
        return timed_out
    
    async def start_background_check(self, check_interval_ms: float = 100) -> None:
        """
        Start background timeout checking.
        
        Args:
            check_interval_ms: How often to check for timeouts
        """
        if self._background_running:
            return
        
        self._background_running = True
        self._check_task = asyncio.create_task(
            self._check_loop(check_interval_ms / 1000.0)
        )
        self.logger.info("Background timeout check started")
    
    async def _check_loop(self, interval_secs: float) -> None:
        """Background loop that checks for timeouts."""
        while self._background_running:
            try:
                await self.check_timeouts()
            except Exception as e:
                self.logger.error(
                    "Error checking timeouts",
                    context={"error": str(e)},
                )
            
            await asyncio.sleep(interval_secs)
    
    async def stop_background_check(self) -> None:
        """Stop background timeout checking."""
        self._background_running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
    
    def get_active_rounds(self) -> dict[str, ActiveRound]:
        """Get all currently tracked rounds."""
        return dict(self._active_rounds)
    
    def get_round_info(self, round_id: str) -> Optional[ActiveRound]:
        """Get info about a specific round."""
        return self._active_rounds.get(round_id)
    
    def __repr__(self) -> str:
        return f"TimeoutManager(active_rounds={len(self._active_rounds)}, timeout_secs={self.timeout_secs})"
