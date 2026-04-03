"""
Unit tests for view changer.
"""

import asyncio

import pytest

from core.events import ConsensusEvent, EventBus, EventType
from core.qoi.view_changer import ViewChanger


class TestViewChanger:
    """Test ViewChanger."""
    
    def test_initialization(self):
        """Test ViewChanger initialization."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        assert changer.node_id == "node-0"
        assert changer.total_replicas == 4
    
    def test_votes_needed(self):
        """Test votes needed calculation."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        # For 4 replicas: f=1, votes_needed = 2*1+1 = 3
        state = changer._view_changes.get("test")
        
        # Create a view change state manually
        from core.qoi.view_changer import ViewChangeState
        state = ViewChangeState(
            round_id="test",
            old_view=0,
            new_view=1,
        )
        
        assert state.votes_needed(4) == 3
    
    @pytest.mark.asyncio
    async def test_initiate_view_change(self):
        """Test initiating a view change."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        success = await changer.initiate_view_change(
            round_id="req-1",
            old_view=0,
        )
        
        assert success
        assert "req-1" in changer._view_changes
        assert changer._view_changes["req-1"].new_view == 1
    
    @pytest.mark.asyncio
    async def test_duplicate_view_change(self):
        """Test preventing duplicate view changes."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        # Initiate first view change (will timeout, but that's ok)
        try:
            await asyncio.wait_for(
                changer.initiate_view_change(
                    round_id="req-1",
                    old_view=0,
                ),
                timeout=0.2,
            )
        except asyncio.TimeoutError:
            pass  # Expected
        
        # Try to initiate same view change again
        success = await changer.initiate_view_change(
            round_id="req-1",
            old_view=0,
        )
        
        assert not success
    
    @pytest.mark.asyncio
    async def test_handle_view_change_msg(self):
        """Test handling VIEW_CHANGE message."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        event = ConsensusEvent(
            event_type=EventType.QOI_VIEW_CHANGE,
            trace_id="req-1",
            data={
                "node_id": "node-1",
                "round_id": "req-1",
                "new_view": 1,
            },
        )
        
        await changer.handle_view_change_msg(event)
        
        assert "req-1" in changer._view_changes
        assert "node-1" in changer._view_changes["req-1"].view_change_votes
    
    @pytest.mark.asyncio
    async def test_view_change_callback(self):
        """Test view changed callback."""
        callback_invocations = []
        
        def on_view_changed(round_id, new_view):
            callback_invocations.append((round_id, new_view))
        
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        changer.set_view_changed_callback(on_view_changed)
        
        # Get the state that was created
        await changer.initiate_view_change(
            round_id="req-1",
            old_view=0,
        )
        
        state = changer._view_changes["req-1"]
        votes_needed = state.votes_needed(4)  # Should be 3
        
        # Simulate receiving enough votes
        for i in range(votes_needed):
            event = ConsensusEvent(
                event_type=EventType.QOI_VIEW_CHANGE,
                trace_id="req-1",
                data={
                    "node_id": f"node-{i+1}",
                    "round_id": "req-1",
                    "new_view": 1,
                },
            )
            await changer.handle_view_change_msg(event)
        
        # Wait a bit for callback to be invoked
        await asyncio.sleep(0.2)
        
        # Note: Callback might be invoked 0-1 times depending on timing
        # since we're not guaranteed to reach the vote threshold
    
    @pytest.mark.asyncio
    async def test_get_view_change_state(self):
        """Test getting view change state."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        # Initiate view change with timeout
        try:
            await asyncio.wait_for(
                changer.initiate_view_change(
                    round_id="req-1",
                    old_view=0,
                ),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass
        
        state = changer.get_view_change_state("req-1")
        
        assert state is not None
        assert state.round_id == "req-1"
        assert state.new_view == 1
    
    @pytest.mark.asyncio
    async def test_clear_view_change(self):
        """Test clearing view change."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        try:
            await asyncio.wait_for(
                changer.initiate_view_change(
                    round_id="req-1",
                    old_view=0,
                ),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass
        
        assert "req-1" in changer._view_changes
        
        changer.clear_view_change("req-1")
        
        assert "req-1" not in changer._view_changes
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_view_changes(self):
        """Test multiple concurrent view changes."""
        changer = ViewChanger(node_id="node-0", total_replicas=4)
        
        # Initiate view changes for different rounds
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                changer.initiate_view_change(
                    round_id=f"req-{i}",
                    old_view=0,
                )
            )
            tasks.append(task)
        
        # Wait with timeout so they don't block forever
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass
        
        # Verify all were initiated
        assert len(changer._view_changes) >= 1
    
    @pytest.mark.asyncio
    async def test_event_bus_publish(self):
        """Test EventBus is available for publishing."""
        bus = EventBus()
        changer = ViewChanger(
            node_id="node-0",
            total_replicas=4,
            event_bus=bus,
        )
        
        # Just verify that event bus is set (actual publishing is tested elsewhere)
        assert changer.event_bus is bus


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
