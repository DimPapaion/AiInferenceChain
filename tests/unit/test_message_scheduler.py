"""
Unit tests for message scheduler.
"""

import asyncio

import pytest

from core.qoi.message_scheduler import MessageScheduler
from core.events import ConsensusEvent, EventType


class TestMessageScheduler:
    """Test MessageScheduler."""
    
    @pytest.mark.asyncio
    async def test_immediate_delivery(self):
        """Test scheduling with 0 delay."""
        scheduler = MessageScheduler()
        
        received = []
        
        async def handler(event):
            received.append(event)
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={"request_id": "req-1"},
        )
        
        msg_id = await scheduler.schedule_deliver(
            event=event,
            handler=handler,
            delay_secs=0.0,
        )
        
        assert msg_id is not None
        
        # Wait for delivery
        assert await scheduler.wait_until_empty(timeout_secs=2.0)
        assert len(received) == 1
        assert received[0].trace_id == "trace-1"
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_delayed_delivery(self):
        """Test scheduling with delay."""
        scheduler = MessageScheduler()
        
        received = []
        start_time = asyncio.get_event_loop().time()
        
        async def handler(event):
            received.append((event, asyncio.get_event_loop().time()))
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={},
        )
        
        # Schedule with 0.2 second delay
        await scheduler.schedule_deliver(
            event=event,
            handler=handler,
            delay_secs=0.2,
        )
        
        # Wait for delivery
        assert await scheduler.wait_until_empty(timeout_secs=2.0)
        
        assert len(received) == 1
        elapsed = received[0][1] - start_time
        # Should have waited close to 0.2s (allow 20ms tolerance for 10ms loop)
        assert elapsed >= 0.18
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_multiple_scheduled_messages(self):
        """Test scheduling multiple messages."""
        scheduler = MessageScheduler()
        
        received = []
        
        async def handler(event):
            received.append(event)
        
        # Schedule 5 messages
        for i in range(5):
            event = ConsensusEvent(
                event_type=EventType.QOI_PREPARE,
                trace_id=f"trace-{i}",
                data={"seq": i},
            )
            await scheduler.schedule_deliver(
                event=event,
                handler=handler,
                delay_secs=0.0,
            )
        
        # Wait for all to be delivered
        assert await scheduler.wait_until_empty(timeout_secs=2.0)
        assert len(received) == 5
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_get_scheduled_count(self):
        """Test getting count of scheduled messages."""
        scheduler = MessageScheduler()
        
        async def noop(event):
            pass
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={},
        )
        
        # Schedule with large delay
        await scheduler.schedule_deliver(
            event=event,
            handler=noop,
            delay_secs=10.0,  # Won't deliver in time
        )
        
        count = scheduler.get_scheduled_count()
        assert count == 1
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_stop_scheduler(self):
        """Test stopping scheduler."""
        scheduler = MessageScheduler()
        
        async def noop(event):
            pass
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={},
        )
        
        await scheduler.schedule_deliver(
            event=event,
            handler=noop,
            delay_secs=10.0,
        )
        
        assert scheduler.get_scheduled_count() == 1
        
        # Stop should cancel the task
        await scheduler.stop()
        
        assert scheduler.get_scheduled_count() == 1  # Still in dict but won't deliver
    
    @pytest.mark.asyncio
    async def test_sync_handler(self):
        """Test with synchronous handler."""
        scheduler = MessageScheduler()
        
        received = []
        
        def sync_handler(event):  # Not async
            received.append(event)
        
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-1",
            data={},
        )
        
        await scheduler.schedule_deliver(
            event=event,
            handler=sync_handler,
            delay_secs=0.0,
        )
        
        # Wait for delivery
        await scheduler.wait_until_empty(timeout_secs=2.0)
        assert len(received) == 1
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_varied_delays(self):
        """Test multiple messages with different delays."""
        scheduler = MessageScheduler()
        received = []
        
        async def handler(event):
            received.append(event.data["seq"])
        
        # Schedule messages with different delays
        delays = [0.0, 0.05, 0.1, 0.0, 0.05]
        for i, delay in enumerate(delays):
            event = ConsensusEvent(
                event_type=EventType.QOI_PREPARE,
                trace_id=f"trace-{i}",
                data={"seq": i},
            )
            await scheduler.schedule_deliver(
                event=event,
                handler=handler,
                delay_secs=delay,
            )
        
        # Wait for all
        assert await scheduler.wait_until_empty(timeout_secs=2.0)
        assert len(received) == 5
        
        await scheduler.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
