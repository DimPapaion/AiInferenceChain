"""
Unit tests for EventBus and message handling.

Tests:
- Event subscription and publishing
- Message filtering
- Multiple subscribers
- Error handling
- Metrics tracking
"""

import pytest
from datetime import datetime

from core.events import (
    EventBus, EventType, ConsensusEvent, get_global_bus, reset_global_bus
)
from core.utils.logger import StructuredLogger, get_logger


class TestEventBus:
    """Tests for EventBus."""
    
    def setup_method(self):
        """Reset global bus before each test."""
        reset_global_bus()
    
    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish."""
        bus = EventBus()
        collected = []
        
        def callback(event: ConsensusEvent):
            collected.append(event)
        
        bus.subscribe(EventType.QOI_COMMITTED, callback)
        
        # Publish an event
        event = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            trace_id="test-1",
            data={"consensus_class": 5},
        )
        bus.publish(EventType.QOI_COMMITTED, event)
        
        assert len(collected) == 1
        assert collected[0].event_type == EventType.QOI_COMMITTED
        assert collected[0].data["consensus_class"] == 5
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers to same event."""
        bus = EventBus()
        collected1 = []
        collected2 = []
        
        callback1 = lambda e: collected1.append(e)
        callback2 = lambda e: collected2.append(e)
        
        bus.subscribe(EventType.QOI_COMMITTED, callback1)
        bus.subscribe(EventType.QOI_COMMITTED, callback2)
        
        event = ConsensusEvent(event_type=EventType.QOI_COMMITTED, trace_id="test")
        bus.publish(EventType.QOI_COMMITTED, event)
        
        assert len(collected1) == 1
        assert len(collected2) == 1
    
    def test_event_filter(self):
        """Test event filtering."""
        bus = EventBus()
        collected = []
        
        def callback(event: ConsensusEvent):
            collected.append(event)
        
        def filter_fn(event: ConsensusEvent) -> bool:
            return event.data.get("node_id") == "abc"
        
        bus.subscribe(EventType.QOI_COMMITTED, callback, filter_fn=filter_fn)
        
        # Publish matching event
        event1 = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            data={"node_id": "abc"},
        )
        bus.publish(EventType.QOI_COMMITTED, event1)
        
        # Publish non-matching event
        event2 = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            data={"node_id": "xyz"},
        )
        bus.publish(EventType.QOI_COMMITTED, event2)
        
        assert len(collected) == 1
        assert collected[0].data["node_id"] == "abc"
    
    def test_unsubscribe(self):
        """Test unsubscribing."""
        bus = EventBus()
        collected = []
        callback = lambda e: collected.append(e)
        
        bus.subscribe(EventType.QOI_COMMITTED, callback)
        bus.unsubscribe(EventType.QOI_COMMITTED, callback)
        
        event = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        bus.publish(EventType.QOI_COMMITTED, event)
        
        assert len(collected) == 0
    
    def test_metrics(self):
        """Test event bus metrics."""
        bus = EventBus()
        
        def callback(e):
            pass
        
        bus.subscribe(EventType.QOI_COMMITTED, callback)
        bus.subscribe(EventType.QOI_PREPARE, callback)
        
        metrics = bus.metrics()
        assert metrics["total_subscriptions"] == 2
        assert metrics["subscribed_types"] == 2
        
        # Publish 3 events
        for _ in range(3):
            bus.publish(
                EventType.QOI_COMMITTED,
                ConsensusEvent(event_type=EventType.QOI_COMMITTED),
            )
        
        metrics = bus.metrics()
        assert metrics["total_published"] == 3
    
    def test_error_in_subscriber(self):
        """Test that error in subscriber doesn't crash bus."""
        bus = EventBus()
        collected = []
        
        def bad_callback(e):
            raise ValueError("Intentional error")
        
        def good_callback(e):
            collected.append(e)
        
        bus.subscribe(EventType.QOI_COMMITTED, bad_callback)
        bus.subscribe(EventType.QOI_COMMITTED, good_callback)
        
        # Should not raise even though bad_callback fails
        event = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        bus.publish(EventType.QOI_COMMITTED, event)
        
        # But good_callback should have been called
        assert len(collected) == 1
    
    def test_string_event_type(self):
        """Test using string event types."""
        bus = EventBus()
        collected = []
        callback = lambda e: collected.append(e)
        
        bus.subscribe("qoi_committed", callback)
        
        event = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        bus.publish("qoi_committed", event)
        
        assert len(collected) == 1
    
    def test_global_bus(self):
        """Test global event bus singleton."""
        reset_global_bus()
        
        bus1 = get_global_bus()
        bus2 = get_global_bus()
        
        assert bus1 is bus2
    
    def test_publish_with_data(self):
        """Test publish with inline data."""
        bus = EventBus()
        collected = []
        callback = lambda e: collected.append(e)
        
        bus.subscribe(EventType.QOI_COMMITTED, callback)
        
        # Publish with inline data
        bus.publish(
            EventType.QOI_COMMITTED,
            trace_id="test-1",
            data={"consensus_class": 5, "round": 1},
        )
        
        assert len(collected) == 1
        assert collected[0].data["consensus_class"] == 5
        assert collected[0].trace_id == "test-1"


class TestStructuredLogger:
    """Tests for StructuredLogger."""
    
    def test_logger_creation(self):
        """Test logger creation."""
        logger = StructuredLogger(component="test_component")
        assert logger.component == "test_component"
    
    def test_logger_output_json(self, capsys):
        """Test JSON output."""
        logger = StructuredLogger(component="test", output="json")
        logger.info("Test message", context={"key": "value"})
        
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "key" in captured.out
        assert "value" in captured.out
    
    def test_logger_output_pretty(self, capsys):
        """Test pretty output."""
        logger = StructuredLogger(component="test", output="pretty")
        logger.info("Test message")
        
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "test" in captured.out
    
    def test_logger_levels(self, capsys):
        """Test different log levels."""
        logger = StructuredLogger(component="test", output="pretty")
        
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warn("Warn message")
        logger.error("Error message")
        
        captured = capsys.readouterr()
        assert "DEBUG" in captured.out
        assert "INFO" in captured.out
        assert "WARN" in captured.out
        assert "ERROR" in captured.out
    
    def test_logger_trace_id(self, capsys):
        """Test trace ID in logs."""
        logger = StructuredLogger(component="test", output="pretty")
        logger.info("Message", trace_id="trace-123")
        
        captured = capsys.readouterr()
        assert "trace-123" in captured.out
    
    def test_get_logger_singleton(self):
        """Test logger singleton."""
        logger1 = get_logger("component_a")
        logger2 = get_logger("component_a")
        
        assert logger1 is logger2
    
    def test_get_logger_different_components(self):
        """Test different loggers for different components."""
        logger1 = get_logger("component_a")
        logger2 = get_logger("component_b")
        
        assert logger1 is not logger2
        assert logger1.component == "component_a"
        assert logger2.component == "component_b"


class TestConsensusEvent:
    """Tests for ConsensusEvent."""
    
    def test_event_creation(self):
        """Test consensus event creation."""
        event = ConsensusEvent(
            event_type=EventType.QOI_COMMITTED,
            trace_id="test",
            data={"key": "value"},
        )
        
        assert event.event_type == EventType.QOI_COMMITTED
        assert event.trace_id == "test"
        assert event.data["key"] == "value"
    
    def test_event_default_trace_id(self):
        """Test event defaults to random trace ID."""
        event1 = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        event2 = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        
        assert event1.trace_id != event2.trace_id
        assert len(event1.trace_id) > 0
    
    def test_event_has_timestamp(self):
        """Test event has timestamp."""
        event = ConsensusEvent(event_type=EventType.QOI_COMMITTED)
        assert event.timestamp > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
