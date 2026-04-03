"""
Async wrapper around ConsensusLog for non-blocking persistence.

Allows concurrent rounds by running SQLite operations in a thread pool.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any

from core.events import ConsensusEvent
from core.qoi.consensus_log import ConsensusLog, CheckpointRecord
from core.qoi.state_machine import QoIPhase


class AsyncConsensusLog:
    """
    Async wrapper around ConsensusLog for non-blocking operations.
    
    SQLite is synchronous and blocking. This wrapper runs operations
    in a thread pool to avoid blocking the event loop.
    
    Usage:
        log = AsyncConsensusLog("node.db", max_workers=2)
        await log.record_event(event)
        await log.record_checkpoint(...)
    """
    
    def __init__(
        self,
        db_path: str,
        max_workers: int = 2,
        executor: Optional[ThreadPoolExecutor] = None,
    ):
        """
        Initialize async consensus log.
        
        Args:
            db_path: Path to SQLite database file
            max_workers: Max thread pool workers for blocking ops
            executor: Custom ThreadPoolExecutor (creates one if None)
        """
        self.db_path = db_path
        self.log = ConsensusLog(db_path)
        
        # Thread pool for blocking operations
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)
        self._own_executor = executor is None
    
    async def record_event(self, event: ConsensusEvent) -> None:
        """
        Record a consensus event (async, non-blocking).
        
        Args:
            event: ConsensusEvent to record
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self.log.record_event,
            event,
        )
    
    async def record_checkpoint(
        self,
        round_id: str,
        view: int,
        seq: int,
        phase: QoIPhase | str,
        trace_id: str,
        event_data: dict[str, Any],
    ) -> None:
        """
        Record a consensus checkpoint (async, non-blocking).
        
        Args:
            round_id: Request ID for this round
            view: Current view number
            seq: Sequence number
            phase: QoI phase (enum or string)
            trace_id: Trace ID for debugging
            event_data: Event-specific data to store
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self.log.record_checkpoint,
            round_id,
            view,
            seq,
            phase,
            trace_id,
            event_data,
        )
    
    async def recover_latest_round(self) -> Optional[CheckpointRecord]:
        """
        Recover latest checkpoint (async, non-blocking).
        
        Returns:
            CheckpointRecord or None if no checkpoints exist
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.log.recover_latest_round,
        )
    
    async def get_events_since(
        self,
        round_id: str,
        since_timestamp: float,
    ) -> list[dict]:
        """
        Get events since timestamp (async, non-blocking).
        
        Args:
            round_id: Request ID to filter by
            since_timestamp: Unix timestamp threshold
            
        Returns:
            List of events matching criteria
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.log.get_events_since,
            round_id,
            since_timestamp,
        )
    
    async def get_round_history(self, round_id: str) -> list[dict]:
        """
        Get complete round history (async, non-blocking).
        
        Args:
            round_id: Request ID to retrieve history for
            
        Returns:
            List of all checkpoints + events for this round
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.log.get_round_history,
            round_id,
        )
    
    async def prune_old_rounds(self, keep_rounds: int = 100) -> int:
        """
        Prune old rounds (async, non-blocking).
        
        Args:
            keep_rounds: Keep this many most recent rounds
            
        Returns:
            Number of records deleted
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.log.prune_old_rounds,
            keep_rounds,
        )
    
    async def stats(self) -> dict[str, Any]:
        """
        Get log statistics (async, non-blocking).
        
        Returns:
            Statistics dictionary
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.log.stats,
        )
    
    async def clear(self) -> None:
        """
        Clear all logs (async, non-blocking, testing only).
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self.log.clear,
        )
    
    def close(self) -> None:
        """Close the database (but not executor from here)."""
        self.log.close()
    
    async def close_async(self) -> None:
        """Close asynchronously (non-blocking)."""
        loop = asyncio.get_event_loop()
        # Close the database in executor thread
        await loop.run_in_executor(self._executor, self.log.close)
        # Shutdown executor from default executor (not from self._executor)
        if self._own_executor:
            await loop.run_in_executor(None, self._executor.shutdown, True)
    
    def __repr__(self) -> str:
        return f"AsyncConsensusLog(db_path={self.db_path})"
