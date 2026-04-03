"""
Consensus Log - Write-Ahead Log for QoI consensus state.

Provides:
  - WAL (Write-Ahead Log) for state machine transitions
  - SQLite backend for persistence
  - Checkpoint/recovery mechanism
  - Replay on node restart

Usage:
    log = ConsensusLog("node-0.db")
    
    # Subscribe to state machine events
    bus.subscribe(EventType.QOI_PRE_PREPARE, 
                  lambda e: log.record_event(e))
    
    # On crash + restart:
    recovered_state = log.recover_latest_round()
    # Node resumes exact state from before crash
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from core.events import ConsensusEvent, EventType
from core.qoi.state_machine import QoIPhase
from core.utils.logger import get_logger


@dataclass
class CheckpointRecord:
    """Single checkpoint in the log."""
    
    round_id: str           # request_id
    view: int
    seq: int
    phase: str              # QoIPhase name
    timestamp: float
    trace_id: str
    event_data: dict        # Raw event data
    
    def to_dict(self) -> dict:
        return {
            "round_id": self.round_id,
            "view": self.view,
            "seq": self.seq,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "event_data": self.event_data,
        }


class ConsensusLog:
    """
    Write-Ahead Log for consensus state.
    
    Persists all state machine transitions to SQLite.
    Enables recovery after node crash.
    """
    
    def __init__(self, db_path: str | Path) -> None:
        """Initialize consensus log."""
        self.db_path = Path(db_path)
        self.logger = get_logger(f"consensus_log_{self.db_path.stem}")
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY,
                    round_id TEXT NOT NULL,
                    view INTEGER NOT NULL,
                    seq INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    trace_id TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    round_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Index for fast round lookup
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_round 
                ON checkpoints(round_id, view, seq)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_round 
                ON events(round_id, timestamp)
            """)
            
            conn.commit()
        
        self.logger.info("Consensus log tables ensured")
    
    def record_event(self, event: ConsensusEvent) -> None:
        """
        Record a consensus event.
        
        Called when ANY consensus event occurs (not just phase changes).
        Provides complete event history for auditing.
        """
        round_id = event.data.get("request_id", "unknown")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO events 
                (round_id, event_type, trace_id, event_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                round_id,
                event.event_type.value,
                event.trace_id,
                json.dumps(event.data),
                event.timestamp,
            ))
            conn.commit()
    
    def record_checkpoint(
        self,
        round_id: str,
        view: int,
        seq: int,
        phase: QoIPhase | str,
        trace_id: str,
        event_data: dict[str, Any],
    ) -> None:
        """
        Record a state machine checkpoint.
        
        Called before major phase transitions.
        Checkpoints allow fast recovery without replaying all events.
        """
        phase_str = phase.name if isinstance(phase, QoIPhase) else str(phase)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO checkpoints
                (round_id, view, seq, phase, timestamp, trace_id, event_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                round_id,
                view,
                seq,
                phase_str,
                time.time(),
                trace_id,
                json.dumps(event_data),
            ))
            conn.commit()
        
        self.logger.info(
            "Checkpoint recorded",
            trace_id=trace_id,
            context={"round": round_id, "phase": phase_str},
        )
    
    def recover_latest_round(self) -> Optional[CheckpointRecord]:
        """
        Recover the latest checkpoint.
        
        Used on node startup to resume interrupted consensus round.
        Returns None if no checkpoints exist.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT round_id, view, seq, phase, timestamp, trace_id, event_data
                FROM checkpoints
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
        
        if row is None:
            self.logger.info("No checkpoints found; starting fresh")
            return None
        
        round_id, view, seq, phase, timestamp, trace_id, event_data_json = row
        
        checkpoint = CheckpointRecord(
            round_id=round_id,
            view=view,
            seq=seq,
            phase=phase,
            timestamp=timestamp,
            trace_id=trace_id,
            event_data=json.loads(event_data_json),
        )
        
        self.logger.info(
            "Recovered checkpoint",
            trace_id=trace_id,
            context={
                "round": round_id,
                "phase": phase,
                "view": view,
            },
        )
        
        return checkpoint
    
    def get_events_since(
        self,
        round_id: str,
        since_timestamp: float,
    ) -> list[dict]:
        """
        Get all events for a round since a given timestamp.
        
        Used to replay events after recovery.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT event_type, trace_id, event_data, timestamp
                FROM events
                WHERE round_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (round_id, since_timestamp))
            
            rows = cursor.fetchall()
        
        return [
            {
                "event_type": row[0],
                "trace_id": row[1],
                "event_data": json.loads(row[2]),
                "timestamp": row[3],
            }
            for row in rows
        ]
    
    def get_round_history(self, round_id: str) -> list[dict]:
        """Get complete history of a round (all checkpoints and events)."""
        with sqlite3.connect(self.db_path) as conn:
            # Get checkpoints
            cursor = conn.execute("""
                SELECT 'checkpoint' as type, phase as label, timestamp, event_data
                FROM checkpoints
                WHERE round_id = ?
                UNION ALL
                SELECT 'event' as type, event_type as label, timestamp, event_data
                FROM events
                WHERE round_id = ?
                ORDER BY timestamp ASC
            """, (round_id, round_id))
            
            rows = cursor.fetchall()
        
        return [
            {
                "type": row[0],
                "label": row[1],
                "timestamp": row[2],
                "data": json.loads(row[3]),
            }
            for row in rows
        ]
    
    def prune_old_rounds(self, keep_rounds: int = 100) -> int:
        """
        Delete old checkpoints to save space.
        
        Keeps the most recent N complete rounds.
        Returns number of records deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get all distinct round IDs, ordered by latest timestamp
            cursor = conn.execute("""
                SELECT round_id
                FROM (
                    SELECT round_id, MAX(timestamp) as latest_ts
                    FROM checkpoints
                    GROUP BY round_id
                    ORDER BY latest_ts DESC
                )
                LIMIT -1 OFFSET ?
            """, (keep_rounds,))
            
            old_round_ids = [row[0] for row in cursor.fetchall()]
            
            if not old_round_ids:
                return 0
            
            # Delete events and checkpoints for old rounds
            placeholders = ",".join("?" * len(old_round_ids))
            
            cursor = conn.execute(
                f"DELETE FROM events WHERE round_id IN ({placeholders})",
                old_round_ids,
            )
            events_deleted = cursor.rowcount
            
            cursor = conn.execute(
                f"DELETE FROM checkpoints WHERE round_id IN ({placeholders})",
                old_round_ids,
            )
            checkpoints_deleted = cursor.rowcount
            
            conn.commit()
        
        total_deleted = events_deleted + checkpoints_deleted
        self.logger.info(
            "Pruned old rounds",
            context={
                "old_rounds": len(old_round_ids),
                "records_deleted": total_deleted,
            },
        )
        
        return total_deleted
    
    def stats(self) -> dict[str, Any]:
        """Return log statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Count records
            cursor = conn.execute("SELECT COUNT(*) FROM checkpoints")
            checkpoint_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM events")
            event_count = cursor.fetchone()[0]
            
            # Get distinct rounds
            cursor = conn.execute(
                "SELECT COUNT(DISTINCT round_id) FROM checkpoints"
            )
            round_count = cursor.fetchone()[0]
            
            # Get db size
            cursor = conn.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            db_size = cursor.fetchone()[0]
        
        return {
            "checkpoint_count": checkpoint_count,
            "event_count": event_count,
            "round_count": round_count,
            "db_size_bytes": db_size,
        }
    
    def clear(self) -> None:
        """Clear all logs (testing only)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM checkpoints")
            conn.execute("DELETE FROM events")
            conn.commit()
        
        self.logger.warn("Consensus log cleared")
    
    def close(self) -> None:
        """Close the database connection and cleanup."""
        # SQLite connections are closed when the context manager exits,
        # so this is mainly a no-op for interface compatibility.
        # However, we can track that close was called if needed.
        pass
    
    def __repr__(self) -> str:
        stats = self.stats()
        return (
            f"ConsensusLog(path={self.db_path}, "
            f"checkpoints={stats['checkpoint_count']}, "
            f"events={stats['event_count']}, "
            f"rounds={stats['round_count']})"
        )
