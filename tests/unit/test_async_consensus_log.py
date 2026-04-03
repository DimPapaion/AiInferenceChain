"""
Unit tests for async consensus log.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from core.qoi.async_consensus_log import AsyncConsensusLog
from core.qoi.consensus_log import ConsensusLog
from core.qoi.state_machine import QoIPhase
from core.events import ConsensusEvent, EventType


class TestAsyncConsensusLog:
    """Test AsyncConsensusLog wrapper."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "async_test.db")
            yield db_path
    
    @pytest.mark.asyncio
    async def test_async_record_event(self, temp_db):
        """Test recording events asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={"request_id": "req-1", "view": 0},
        )
        
        # Record asynchronously
        await log.record_event(event)
        
        # Verify it was recorded
        stats = await log.stats()
        assert stats["event_count"] == 1
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_record_checkpoint(self, temp_db):
        """Test recording checkpoints asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        await log.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={"predicted_class": 5},
        )
        
        stats = await log.stats()
        assert stats["checkpoint_count"] == 1
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_recover_latest_round(self, temp_db):
        """Test recovering checkpoints asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        await log.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PREPARE,
            trace_id="trace-1",
            event_data={"predicted_class": 5},
        )
        
        checkpoint = await log.recover_latest_round()
        assert checkpoint is not None
        assert checkpoint.round_id == "req-1"
        assert checkpoint.phase == "PREPARE"
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_db):
        """Test concurrent async operations."""
        log = AsyncConsensusLog(temp_db, max_workers=4)
        
        # Start multiple operations concurrently
        tasks = []
        for i in range(5):
            task = log.record_checkpoint(
                round_id=f"req-{i}",
                view=0,
                seq=i,
                phase=QoIPhase.PRE_PREPARE,
                trace_id=f"trace-{i}",
                event_data={"round": i},
            )
            tasks.append(task)
        
        # Wait for all to complete
        await asyncio.gather(*tasks)
        
        # Verify all were recorded
        stats = await log.stats()
        assert stats["checkpoint_count"] == 5
        assert stats["round_count"] == 5
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_get_round_history(self, temp_db):
        """Test retrieving history asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        await log.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={},
        )
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-2",
            data={"request_id": "req-1"},
        )
        await log.record_event(event)
        
        history = await log.get_round_history("req-1")
        assert len(history) >= 2
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_prune(self, temp_db):
        """Test pruning old rounds asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        # Record 5 rounds
        for i in range(5):
            await log.record_checkpoint(
                round_id=f"req-{i}",
                view=0,
                seq=i,
                phase=QoIPhase.COMMITTED,
                trace_id=f"trace-{i}",
                event_data={},
            )
        
        stats = await log.stats()
        assert stats["round_count"] == 5
        
        # Prune to keep only 2
        deleted = await log.prune_old_rounds(keep_rounds=2)
        assert deleted > 0
        
        stats = await log.stats()
        assert stats["round_count"] == 2
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_clear(self, temp_db):
        """Test clearing log asynchronously."""
        log = AsyncConsensusLog(temp_db)
        
        await log.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.COMMITTED,
            trace_id="trace-1",
            event_data={},
        )
        
        stats = await log.stats()
        assert stats["checkpoint_count"] == 1
        
        await log.clear()
        
        stats = await log.stats()
        assert stats["checkpoint_count"] == 0
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_async_close(self, temp_db):
        """Test closing async log."""
        log = AsyncConsensusLog(temp_db)
        
        await log.record_event(
            ConsensusEvent(
                event_type=EventType.QOI_COMMITTED,
                trace_id="trace-1",
                data={},
            )
        )
        
        # Close asynchronously
        await log.close_async()
        
        # Can still open same DB
        log2 = ConsensusLog(temp_db)
        stats = log2.stats()
        assert stats["event_count"] == 1
        log2.close()
    
    @pytest.mark.asyncio
    async def test_wrapped_log_still_works(self, temp_db):
        """Test that underlying log is still accessible."""
        log = AsyncConsensusLog(temp_db)
        
        # Use async methods
        await log.record_checkpoint(
            round_id="req-1",
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={},
        )
        
        # Check via underlying log (sync)
        checkpoint = log.log.recover_latest_round()
        assert checkpoint is not None
        assert checkpoint.round_id == "req-1"
        
        log.close()
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_rounds(self, temp_db):
        """Test multiple concurrent rounds in same log."""
        log = AsyncConsensusLog(temp_db, max_workers=4)
        
        async def run_round(round_num):
            for phase_idx, phase in enumerate([QoIPhase.PRE_PREPARE, QoIPhase.PREPARE, QoIPhase.COMMIT]):
                await log.record_checkpoint(
                    round_id=f"req-{round_num}",
                    view=0,
                    seq=round_num,
                    phase=phase,
                    trace_id=f"trace-{round_num}-{phase_idx}",
                    event_data={"round": round_num},
                )
        
        # Run 3 rounds concurrently
        await asyncio.gather(
            run_round(0),
            run_round(1),
            run_round(2),
        )
        
        stats = await log.stats()
        assert stats["round_count"] == 3
        assert stats["checkpoint_count"] == 9
        
        log.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
