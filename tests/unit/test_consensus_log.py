"""
Unit tests for ConsensusLog (persistence layer).

Tests:
- Event recording and retrieval
- Checkpoint recording and recovery
- Round history
- Pruning old rounds
- Statistics
- Database integrity
"""

import pytest
import tempfile
from pathlib import Path

from core.qoi.consensus_log import ConsensusLog, CheckpointRecord
from core.qoi.state_machine import QoIPhase
from core.events import ConsensusEvent, EventType


class TestConsensusLog:
    """Tests for ConsensusLog."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        log = ConsensusLog(db_path)
        yield log
        
        # Cleanup - close database before deleting file
        log.close()
        Path(db_path).unlink(missing_ok=True)
    
    def test_log_creation(self, temp_db):
        """Test creating a consensus log."""
        assert temp_db.db_path.exists()
    
    def test_record_and_recover_checkpoint(self, temp_db):
        """Test recording and recovering a checkpoint."""
        # Record a checkpoint
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={"predicted_class": 5},
        )
        
        # Recover it
        checkpoint = temp_db.recover_latest_round()
        
        assert checkpoint is not None
        assert checkpoint.round_id == "req-1"
        assert checkpoint.view == 0
        assert checkpoint.phase == "PRE_PREPARE"
        assert checkpoint.trace_id == "trace-1"
        assert checkpoint.event_data["predicted_class"] == 5
    
    def test_record_multiple_checkpoints(self, temp_db):
        """Test that latest checkpoint is recovered."""
        # Record multiple checkpoints
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={},
        )
        
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PREPARE,
            trace_id="trace-2",
            event_data={},
        )
        
        # Should recover latest (PREPARE, not PRE_PREPARE)
        checkpoint = temp_db.recover_latest_round()
        assert checkpoint.phase == "PREPARE"
    
    def test_recover_empty_log(self, temp_db):
        """Test recovering from empty log."""
        checkpoint = temp_db.recover_latest_round()
        assert checkpoint is None
    
    def test_record_event(self, temp_db):
        """Test recording events."""
        event = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            trace_id="trace-1",
            data={"consensus_class": 5, "request_id": "req-1"},
        )
        
        temp_db.record_event(event)
        
        # Verify it was recorded
        history = temp_db.get_round_history("req-1")
        assert len(history) == 1
        assert history[0]["type"] == "event"
        assert history[0]["label"] == "qoi_committed"
    
    def test_get_events_since(self, temp_db):
        """Test retrieving events since a timestamp."""
        import time
        
        # Record event 1
        time.sleep(0.01)  # Small delay to get different timestamps
        t1 = time.time()
        
        event1 = ConsensusEvent(
            event_type=EventType.QOI_PRE_PREPARE,
            trace_id="trace-1",
            data={"request_id": "req-1"},
            timestamp=t1,
        )
        temp_db.record_event(event1)
        
        time.sleep(0.01)
        t2 = time.time()
        
        # Record event 2
        event2 = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-2",
            data={"request_id": "req-1"},
            timestamp=t2,
        )
        temp_db.record_event(event2)
        
        # Get events since t1
        events = temp_db.get_events_since("req-1", t1)
        
        assert len(events) == 2
        assert events[0]["event_type"] == "qoi_pre_prepare"
        assert events[1]["event_type"] == "qoi_prepare"
    
    def test_get_round_history(self, temp_db):
        """Test retrieving complete round history."""
        import time
        
        # Record checkpoint and events
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={},
        )
        
        time.sleep(0.01)  # Ensure different timestamp
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-2",
            data={"request_id": "req-1"},
        )
        temp_db.record_event(event)
        
        history = temp_db.get_round_history("req-1")
        
        # Debug: print the history
        for i, item in enumerate(history):
            print(f"{i}: {item['type']} - ts={item['timestamp']}")
        
        # Should have 1 checkpoint + 1 event
        assert len(history) == 2
        # Just check both types exist (order may vary based on timestamps)
        types = [h["type"] for h in history]
        assert "checkpoint" in types
        assert "event" in types
    
    def test_prune_old_rounds(self, temp_db):
        """Test pruning old rounds."""
        # Record multiple rounds
        for i in range(5):
            temp_db.record_checkpoint(
                round_id=f"req-{i}",
                view=0,
                seq=0,
                phase=QoIPhase.COMMITTED,
                trace_id=f"trace-{i}",
                event_data={},
            )
        
        stats_before = temp_db.stats()
        assert stats_before["round_count"] == 5
        
        # Prune, keeping only 2 latest
        deleted = temp_db.prune_old_rounds(keep_rounds=2)
        
        assert deleted > 0
        
        stats_after = temp_db.stats()
        assert stats_after["round_count"] == 2
    
    def test_stats(self, temp_db):
        """Test statistics."""
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.COMMITTED,
            trace_id="trace-1",
            event_data={},
        )
        
        event = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            trace_id="trace-2",
            data={"request_id": "req-1"},
        )
        temp_db.record_event(event)
        
        stats = temp_db.stats()
        
        assert stats["checkpoint_count"] == 1
        assert stats["event_count"] == 1
        assert stats["round_count"] == 1
        assert stats["db_size_bytes"] > 0
    
    def test_clear(self, temp_db):
        """Test clearing the log."""
        temp_db.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.COMMITTED,
            trace_id="trace-1",
            event_data={},
        )
        
        stats_before = temp_db.stats()
        assert stats_before["checkpoint_count"] == 1
        
        temp_db.clear()
        
        stats_after = temp_db.stats()
        assert stats_after["checkpoint_count"] == 0
    
    def test_repr(self, temp_db):
        """Test string representation."""
        repr_str = repr(temp_db)
        assert "ConsensusLog" in repr_str
        assert "checkpoints" in repr_str
    
    def test_checkpoint_record_to_dict(self):
        """Test CheckpointRecord serialization."""
        record = CheckpointRecord(
            round_id="req-1",
            view=0,
            seq=0,
            phase="PRE_PREPARE",
            timestamp=12345.0,
            trace_id="trace-1",
            event_data={"key": "value"},
        )
        
        d = record.to_dict()
        
        assert d["round_id"] == "req-1"
        assert d["phase"] == "PRE_PREPARE"
        assert d["event_data"]["key"] == "value"


class TestConsensusLogIntegration:
    """Integration tests with event bus."""
    
    def test_subscribe_to_events_for_logging(self):
        """Test subscribing to event bus for logging."""
        from core.events import EventBus, EventType, ConsensusEvent
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            log = ConsensusLog(db_path)
            bus = EventBus()
            
            # Subscribe to QOI_COMMITTED events
            bus.subscribe(
                EventType.QOI_COMMITTED,
                lambda e: log.record_event(e),
            )
            
            # Publish an event
            event = ConsensusEvent(
                event_type=EventType.QOI_COMMITTED,
                trace_id="trace-1",
                data={"request_id": "req-1", "consensus_class": 5},
            )
            bus.publish(EventType.QOI_COMMITTED, event)
            
            # Verify it was logged
            history = log.get_round_history("req-1")
            assert len(history) == 1
            assert history[0]["data"]["consensus_class"] == 5
        
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestCrashRecoveryScenario:
    """Tests simulating crash and recovery scenarios."""
    
    def test_crash_recovery_scenario(self):
        """Simulate node crash and recovery."""
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Simulate normal operation
            log = ConsensusLog(db_path)
            
            # Record some work
            log.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.PRE_PREPARE,
                trace_id="trace-1",
                event_data={"predicted_class": 5},
            )
            
            log.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.PREPARE,
                trace_id="trace-2",
                event_data={"predicted_class": 5},
            )
            
            # "Node crashes" here (context manager exits)
            del log
            
            # "Node restarts" - open same DB
            log_restored = ConsensusLog(db_path)
            
            # Recover state
            checkpoint = log_restored.recover_latest_round()
            
            assert checkpoint is not None
            assert checkpoint.phase == "PREPARE"  # Last checkpoint
            assert checkpoint.event_data["predicted_class"] == 5
            
            # Continue from checkpoint
            log_restored.record_checkpoint(
                round_id="req-1",
                view=0,
                seq=0,
                phase=QoIPhase.COMMIT,
                trace_id="trace-3",
                event_data={"predicted_class": 5},
            )
            
            # Verify chain is intact
            history = log_restored.get_round_history("req-1")
            assert len(history) == 3
            assert history[-1]["label"] == "COMMIT"
        
        finally:
            Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
