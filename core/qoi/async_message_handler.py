"""
Async wrapper for QoI message handler.

Enables non-blocking consensus message processing with concurrent round handling.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from core.qoi.message_handler import QoIMessageHandler
from core.qoi.messages import BaseMessage
from core.utils.logger import get_logger


class AsyncQoIMessageHandler:
    """
    Async wrapper around QoIMessageHandler.
    
    Allows concurrent consensus rounds by wrapping blocking operations
    with asyncio and ThreadPoolExecutor patterns.
    
    Usage:
        handler = AsyncQoIMessageHandler(msg_handler)
        
        # Handle messages asynchronously
        await handler.handle_message(message)
    """
    
    def __init__(
        self,
        message_handler: QoIMessageHandler,
        executor = None,
    ):
        """
        Initialize async message handler.
        
        Args:
            message_handler: Base QoIMessageHandler to wrap
            executor: Optional ThreadPoolExecutor for blocking ops
        """
        self.message_handler = message_handler
        self.executor = executor
        self.logger = get_logger("async_message_handler")
        
        self._own_executor = executor is None
        if self._own_executor:
            from concurrent.futures import ThreadPoolExecutor
            self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def handle_message(self, message: BaseMessage) -> None:
        """
        Handle consensus message asynchronously.
        
        Args:
            message: BaseMessage to handle
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            self.message_handler.on_message_received,
            message,
        )
        
        self.logger.debug(
            "Message handled",
            context={"msg_type": type(message).__name__},
        )
    
    async def start_round_async(
        self,
        request_id: str,
        image_hash: str,
        seq: int,
        own_probs: list[float],
        trace_id: Optional[str] = None,
    ) -> None:
        """
        Start a new consensus round asynchronously.
        
        Args:
            request_id: Request ID
            image_hash: Hash of input image
            seq: Sequence number
            own_probs: Model output probabilities
            trace_id: Optional trace ID
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            self.message_handler.start_round,
            request_id,
            image_hash,
            seq,
            own_probs,
            trace_id,
        )
        
        self.logger.debug(
            "Round started",
            trace_id=trace_id,
            context={"request_id": request_id},
        )
    
    async def close_async(self) -> None:
        """Shutdown executor asynchronously."""
        loop = asyncio.get_event_loop()
        if self._own_executor:
            await loop.run_in_executor(None, self.executor.shutdown, True)
    
    def __repr__(self) -> str:
        return f"AsyncQoIMessageHandler(wrapped={self.message_handler})"
