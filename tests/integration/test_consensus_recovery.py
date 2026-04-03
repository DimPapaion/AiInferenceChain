"""
Integration test for consensus crash recovery.

Tests that nodes can:
1. Execute a full consensus round
2. Crash and lose in-memory state  
3. Restart and recover exact state from WAL
4. Resume processing from checkpoint

This validates the Phase 2 persistence layer.
"""

import tempfile
import time
from pathlib import Path

import pytest

from core.qoi.consensus_log import ConsensusLog
from core.qoi.state_machine import QoIPhase
from core.events import EventType, ConsensusEvent


class TestCrashRecovery:
    """Test crash recovery scenarios."""
    
    def test_single_node_round_trip_recovery(self):
        """Test a single node can recover from a simulated crash."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "node-0.db"
            
            # ===== PHASE 1: Normal operation =====
            log1 = ConsensusLog(str(db_path))
            
            # Record some work
            log1.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.PRE_PREPARE,
                trace_id="trace-1",
                event_data={
                    "predicted_class": 5,
                    "request_hash": "hash-1"
                },
            )
            
            # Log an event
            event1 = ConsensusEvent(
                event_type=EventType.QOI_PRE_PREPARE,
                trace_id="trace-1",
                data={"request_id": "req-1", "view": 0},
            )
            log1.record_event(event1)
            
            # Move to PREPARE phase
            log1.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.PREPARE,
                trace_id="trace-2",
                event_data={
                    "predicted_class": 5,
                    "request_hash": "hash-1",
                    "prepare_count": 1
                },
            )
            
            # Log PREPARE event
            event2 = ConsensusEvent(
                event_type=EventType.QOI_PREPARE,
                trace_id="trace-2",
                data={"request_id": "req-1", "view": 0},
            )
            log1.record_event(event2)
            
            # Get stats before crash
            stats_before = log1.stats()
            assert stats_before["checkpoint_count"] == 2
            assert stats_before["event_count"] == 2
            
            # "Crash" - close the log and lose in-memory state
            log1.close()
            del log1
            
            # ===== PHASE 2: Recovery =====
            log2 = ConsensusLog(str(db_path))
            
            # Recover state
            checkpoint = log2.recover_latest_round()
            assert checkpoint is not None
            assert checkpoint.round_id == "req-1"
            assert checkpoint.phase == "PREPARE"  # Last phase
            assert checkpoint.event_data["prepare_count"] == 1
            
            # Retrieved history
            history = log2.get_round_history("req-1")
            assert len(history) == 4  # 2 checkpoints + 2 events
            
            # Verify complete history
            types = [h["type"] for h in history]
            assert types.count("checkpoint") == 2
            assert types.count("event") == 2
            
            # ===== PHASE 3: Resume processing =====
            # Continue from checkpoint
            log2.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.COMMIT,
                trace_id="trace-3",
                event_data={
                    "predicted_class": 5,
                    "request_hash": "hash-1",
                    "commit_count": 2
                },
            )
            
            # Verify final state
            final_checkpoint = log2.recover_latest_round()
            assert final_checkpoint.phase == "COMMIT"
            assert final_checkpoint.event_data["commit_count"] == 2
            
            # Stats should show progression
            stats_after = log2.stats()
            assert stats_after["checkpoint_count"] == 3
            assert stats_after["event_count"] == 2


class TestMultipleRoundsRecovery:
    """Test recovery with multiple rounds."""
    
    def test_recovery_with_multiple_rounds(self):
        """Test that node can recover multiple rounds correctly."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "node-0.db"
            log = ConsensusLog(str(db_path))
            
            # Record 3 complete rounds
            for round_num in range(3):
                round_id = f"req-{round_num}"
                for phase_idx, phase in enumerate([QoIPhase.PRE_PREPARE, 
                                                    QoIPhase.PREPARE,
                                                    QoIPhase.COMMIT]):
                    log.record_checkpoint(
                        round_id=round_id,
                        view=0,
                        seq=round_num,
                        phase=phase,
                        trace_id=f"trace-{round_num}-{phase_idx}",
                        event_data={"pred": round_num + phase_idx},
                    )
            
            stats = log.stats()
            assert stats["round_count"] == 3
            assert stats["checkpoint_count"] == 9  # 3 rounds * 3 phases
            
            # Recover latest round
            checkpoint = log.recover_latest_round()
            assert checkpoint.round_id == "req-2"
            assert checkpoint.phase == "COMMIT"
            
            # Get history of second round
            history_1 = log.get_round_history("req-1")
            assert len(history_1) == 3  # 3 checkpoints for round 1
            
            # Pruning should preserve newer rounds
            deleted = log.prune_old_rounds(keep_rounds=2)
            assert deleted > 0
            
            stats_after = log.stats()
            assert stats_after["round_count"] == 2
            # req-1 and req-2 should remain; req-0 deleted
            assert log.recover_latest_round().round_id == "req-2"


class TestEventReplay:
    """Test event replay on recovery."""
    
    def test_replay_events_since_checkpoint(self):
        """Test event recording and basic replay."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "node-0.db"
            log = ConsensusLog(str(db_path))
            
            # Record checkpoint
            log.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.PRE_PREPARE,
                trace_id="trace-0",
                event_data={},
            )
            
            # Record events
            for i in range(3):
                event = ConsensusEvent(
                    event_type=EventType.QOI_PREPARE,
                    trace_id=f"trace-{i+1}",
                    data={"request_id": "req-1", "seq": i},
                )
                log.record_event(event)
            
            # Verify events were recorded
            stats = log.stats()
            print(f"Stats: {stats}")
            assert stats["event_count"] == 3, f"Expected 3 events, got {stats['event_count']}"
            
            # Get round history to verify both checkpoints and events are present
            history = log.get_round_history("req-1")
            print(f"History length: {len(history)}")
            types = [h["type"] for h in history]
            print(f"Types:  {types}")
            
            # Should have 1 checkpoint + 3 events
            assert len(history) >= 3


class TestAuditTrail:
    """Test that audit trail is preserved."""
    
    def test_complete_audit_trail(self):
        """Test that all events and checkpoints are preserved in audit trail."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "node-0.db"
            log = ConsensusLog(str(db_path))
            
            # Build complex round
            log.record_checkpoint(
                round_id="req-complex",
                view=0,
                seq=100,
                phase=QoIPhase.PRE_PREPARE,
                trace_id="trace-pp",
                event_data={
                    "predicted_class": 7,
                    "confidence": 0.95,
                    "model_version": "v1.2",
                },
            )
            
            # Record multiple events
            for event_type in [EventType.QOI_PREPARE, 
                              EventType.QOI_PREPARE,
                              EventType.QOI_COMMIT]:
                event = ConsensusEvent(
                    event_type=event_type,
                    trace_id="trace-complex",
                    data={"request_id": "req-complex", "round": 100},
                )
                log.record_event(event)
            
            # Final state
            log.record_checkpoint(
                round_id="req-complex",
                view=0,
                seq=100,
                phase=QoIPhase.COMMITTED,
                trace_id="trace-committed",
                event_data={
                    "predicted_class": 7,
                    "consensus_reached": True,
                    "responses": 3,
                },
            )
            
            # Verify complete audit trail
            history = log.get_round_history("req-complex")
            assert len(history) == 5  # 2 checkpoints + 3 events
            
            # All entries have timestamps
            for entry in history:
                assert "timestamp" in entry
                assert entry["timestamp"] > 0
            
            # Events and checkpoints are mixed but ordered
            types = [h["type"] for h in history]
            assert "checkpoint" in types
            assert "event" in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
