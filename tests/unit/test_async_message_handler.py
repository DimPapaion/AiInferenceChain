"""
Unit tests for async message handler.
"""

import asyncio

import pytest

from core.qoi.async_message_handler import AsyncQoIMessageHandler
from core.qoi.message_handler import QoIMessageHandler, QoIMessageHandlerConfig


def create_test_handler():
    """Create a test message handler."""
    config = QoIMessageHandlerConfig(
        node_id="node-0",
        primary_id="node-0",
        f=1,
    )
    return QoIMessageHandler(config=config)


class TestAsyncQoIMessageHandler:
    """Test AsyncQoIMessageHandler."""
    
    def test_initialization(self):
        """Test initialization."""
        msg_handler = create_test_handler()
        async_handler = AsyncQoIMessageHandler(msg_handler)
        
        assert async_handler.message_handler is msg_handler
        assert async_handler._own_executor is True
    
    @pytest.mark.asyncio
    async def test_start_round_async(self):
        """Test starting a round asynchronously."""
        msg_handler = create_test_handler()
        async_handler = AsyncQoIMessageHandler(msg_handler)
        
        # Should not raise
        await async_handler.start_round_async(
            request_id="req-1",
            image_hash="hash-1",
            seq=1,
            own_probs=[0.1, 0.2, 0.7],
            trace_id="trace-1",
        )
    
    @pytest.mark.asyncio
    async def test_multiple_rounds_concurrent(self):
        """Test starting multiple rounds concurrently."""
        msg_handler = create_test_handler()
        async_handler = AsyncQoIMessageHandler(msg_handler)
        
        tasks = [
            async_handler.start_round_async(
                request_id=f"req-{i}",
                image_hash=f"hash-{i}",
                seq=i,
                own_probs=[0.1, 0.2, 0.7],
                trace_id=f"trace-{i}",
            )
            for i in range(5)
        ]
        
        # All should complete without error
        await asyncio.gather(*tasks)
    
    @pytest.mark.asyncio
    async def test_custom_executor(self):
        """Test with custom thread pool executor."""
        from concurrent.futures import ThreadPoolExecutor
        
        executor = ThreadPoolExecutor(max_workers=2)
        msg_handler = create_test_handler()
        
        async_handler = AsyncQoIMessageHandler(
            msg_handler,
            executor=executor,
        )
        
        assert async_handler._own_executor is False
        
        # Test that we can still use it
        await async_handler.start_round_async(
            request_id="req-1",
            image_hash="hash-1",
            seq=1,
            own_probs=[0.1, 0.2, 0.7],
        )
        
        # Cleanup
        executor.shutdown(wait=True)
    
    @pytest.mark.asyncio
    async def test_close_async(self):
        """Test closing async handler."""
        msg_handler = create_test_handler()
        async_handler = AsyncQoIMessageHandler(msg_handler)
        
        # Should not raise
        await async_handler.close_async()
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_concurrent(self):
        """Test multiple handlers processing rounds concurrently."""
        handlers = [
            AsyncQoIMessageHandler(create_test_handler())
            for _ in range(3)
        ]
        
        tasks = []
        for i, handler in enumerate(handlers):
            for j in range(2):
                task = handler.start_round_async(
                    request_id=f"req-{i}-{j}",
                    image_hash=f"hash-{i}-{j}",
                    seq=j,
                    own_probs=[0.1, 0.2, 0.7],
                )
                tasks.append(task)
        
        # All should complete without error
        await asyncio.gather(*tasks)
    
    @pytest.mark.asyncio
    async def test_stress_many_rounds(self):
        """Test handling many rounds rapidly."""
        msg_handler = create_test_handler()
        async_handler = AsyncQoIMessageHandler(msg_handler)
        
        tasks = [
            async_handler.start_round_async(
                request_id=f"req-{i}",
                image_hash=f"hash-{i}",
                seq=i,
                own_probs=[0.1, 0.2, 0.7],
            )
            for i in range(20)
        ]
        
        # Start 20 rounds concurrently
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
