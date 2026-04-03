"""
Unit tests for timeout manager.
"""

import asyncio

import pytest

from core.qoi.timeout_manager import TimeoutManager


class TestTimeoutManager:
    """Test TimeoutManager."""
    
    def test_start_round(self):
        """Test starting a round."""
        manager = TimeoutManager(timeout_secs=1.0)
        
        manager.start_round(round_id="req-1", view=0)
        
        assert "req-1" in manager.get_active_rounds()
        assert manager.get_round_info("req-1").view == 0
    
    def test_end_round(self):
        """Test ending a round."""
        manager = TimeoutManager(timeout_secs=1.0)
        
        manager.start_round(round_id="req-1", view=0)
        manager.end_round(round_id="req-1")
        
        assert "req-1" not in manager.get_active_rounds()
    
    def test_update_view(self):
        """Test updating view number."""
        manager = TimeoutManager(timeout_secs=1.0)
        
        manager.start_round(round_id="req-1", view=0)
        manager.update_view(round_id="req-1", new_view=1)
        
        assert manager.get_round_info("req-1").view == 1
    
    def test_elapsed_time(self):
        """Test elapsed time tracking."""
        manager = TimeoutManager(timeout_secs=10.0)
        
        manager.start_round(round_id="req-1", view=0)
        elapsed = manager.get_round_info("req-1").elapsed_secs
        
        assert elapsed >= 0.0
        assert elapsed < 0.5  # Should be very small
    
    @pytest.mark.asyncio
    async def test_no_timeout(self):
        """Test no timeout when time hasn't elapsed."""
        manager = TimeoutManager(timeout_secs=10.0)
        
        manager.start_round(round_id="req-1", view=0)
        
        timed_out = await manager.check_timeouts()
        
        assert len(timed_out) == 0
        assert "req-1" in manager.get_active_rounds()
        
        manager.end_round(round_id="req-1")
    
    @pytest.mark.asyncio
    async def test_timeout_detection(self):
        """Test timeout detection."""
        manager = TimeoutManager(timeout_secs=0.1)
        
        manager.start_round(round_id="req-1", view=0)
        
        # Wait for timeout
        await asyncio.sleep(0.15)
        
        timed_out = await manager.check_timeouts()
        
        assert len(timed_out) == 1
        assert timed_out[0] == ("req-1", 0)  # (round_id, view)
    
    @pytest.mark.asyncio
    async def test_multiple_rounds_timeout(self):
        """Test timeout with multiple rounds."""
        manager = TimeoutManager(timeout_secs=0.1)
        
        manager.start_round(round_id="req-1", view=0)
        manager.start_round(round_id="req-2", view=0)
        manager.start_round(round_id="req-3", view=0)
        
        active = manager.get_active_rounds()
        assert len(active) == 3
        
        # Wait for timeout
        await asyncio.sleep(0.15)
        
        # Check timeouts
        timed_out = await manager.check_timeouts()
        assert len(timed_out) == 3
    
    @pytest.mark.asyncio
    async def test_some_rounds_timeout(self):
        """Test with partial timeout."""
        manager = TimeoutManager(timeout_secs=0.1)
        
        manager.start_round(round_id="req-1", view=0)
        
        await asyncio.sleep(0.15)
        
        manager.start_round(round_id="req-2", view=0)  # After first timeout
        
        timed_out = await manager.check_timeouts()
        
        # Only round 1 should timeout
        assert len(timed_out) == 1
        assert timed_out[0][0] == "req-1"
        
        manager.end_round(round_id="req-2")
    
    @pytest.mark.asyncio
    async def test_timeout_callback(self):
        """Test timeout callback."""
        callback_invocations = []
        
        def on_timeout_callback(round_id, view):
            callback_invocations.append((round_id, view))
        
        manager = TimeoutManager(
            timeout_secs=0.1,
            on_timeout=on_timeout_callback,
        )
        
        manager.start_round(round_id="req-1", view=0)
        
        await asyncio.sleep(0.15)
        
        timed_out = await manager.check_timeouts()
        
        assert len(timed_out) == 1
        assert len(callback_invocations) == 1
        assert callback_invocations[0] == ("req-1", 0)
    
    @pytest.mark.asyncio
    async def test_background_check_loop(self):
        """Test background timeout checking."""
        callback_invocations = []
        
        def on_timeout_callback(round_id, view):
            callback_invocations.append((round_id, view))
        
        manager = TimeoutManager(
            timeout_secs=0.1,
            on_timeout=on_timeout_callback,
        )
        
        manager.start_round(round_id="req-1", view=0)
        
        # Start background checking (check every 50ms)
        await manager.start_background_check(check_interval_ms=50)
        
        # Wait for timeout to be detected
        await asyncio.sleep(0.3)
        
        # Should have called callback
        assert len(callback_invocations) >= 1
        
        await manager.stop_background_check()
    
    @pytest.mark.asyncio
    async def test_multiple_view_changes(self):
        """Test view changes on timeout."""
        manager = TimeoutManager(timeout_secs=0.1)
        
        manager.start_round(round_id="req-1", view=0)
        
        await asyncio.sleep(0.15)
        
        # On timeout, view should change
        manager.update_view(round_id="req-1", new_view=1)
        
        timed_out_again = await manager.check_timeouts()
        
        # Should still timeout because view changed
        # (and then removed from tracking)
        assert len(timed_out_again) >= 1
    
    @pytest.mark.asyncio
    async def test_get_all_active_rounds(self):
        """Test getting all active rounds."""
        manager = TimeoutManager(timeout_secs=1.0)
        
        manager.start_round(round_id="req-1", view=0)
        manager.start_round(round_id="req-2", view=0)
        manager.start_round(round_id="req-3", view=0)
        
        active = manager.get_active_rounds()
        
        assert len(active) == 3
        assert "req-1" in active
        assert "req-2" in active
        assert "req-3" in active
        
        manager.end_round(round_id="req-2")
        
        active = manager.get_active_rounds()
        assert len(active) == 2
        assert "req-2" not in active
        
        manager.end_round(round_id="req-1")
        manager.end_round(round_id="req-3")
    
    @pytest.mark.asyncio
    async def test_is_timed_out(self):
        """Test checking if round is timed out."""
        manager = TimeoutManager(timeout_secs=0.1)
        
        manager.start_round(round_id="req-1", view=0)
        
        # Initially not timed out
        assert not manager.get_round_info("req-1").is_timed_out
        
        await asyncio.sleep(0.15)
        
        # Now should be timed out
        assert manager.get_round_info("req-1").is_timed_out
        
        manager.end_round(round_id="req-1")
    
    @pytest.mark.asyncio
    async def test_time_until_timeout(self):
        """Test getting time until timeout."""
        manager = TimeoutManager(timeout_secs=1.0)
        
        manager.start_round(round_id="req-1", view=0)
        
        time_until = manager.get_round_info("req-1").time_until_timeout_secs
        
        assert 0.9 < time_until <= 1.0
        
        manager.end_round(round_id="req-1")
    
    @pytest.mark.asyncio
    async def test_stress_many_rounds(self):
        """Stress test with many concurrent rounds."""
        manager = TimeoutManager(timeout_secs=0.2)
        
        # Start 100 rounds
        for i in range(100):
            manager.start_round(round_id=f"req-{i}", view=0)
        
        active = manager.get_active_rounds()
        assert len(active) == 100
        
        # Wait for timeout
        await asyncio.sleep(0.25)
        
        # Check timeouts
        timed_out = await manager.check_timeouts()
        assert len(timed_out) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
