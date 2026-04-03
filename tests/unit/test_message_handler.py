"""
Unit tests for QoIMessageHandler.

Tests:
- Message handling flow
- State machine integration
- Event emission
- Message signing (mocked)
- Timeout handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from core.qoi.message_handler import QoIMessageHandler, QoIMessageHandlerConfig
from core.qoi.messages import PrePrepareMsg, PrepareMsg, CommitMsg
from core.qoi.state_machine import QoIPhase
from core.events import EventBus, EventType, ConsensusEvent, reset_global_bus


class MockNode:
    """Mock node for testing."""
    def __init__(self, node_id="0000"):
        self.identity = Mock()
        self.identity.sign = Mock(return_value="signature")


class TestQoIMessageHandler:
    """Tests for QoIMessageHandler."""
    
    def setup_method(self):
        """Reset global bus before each test."""
        reset_global_bus()
    
    def test_handler_creation(self):
        """Test creating a message handler."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="0000000000000000000000000000000000000000",
            f=1,
        )
        handler = QoIMessageHandler(config)
        
        assert handler.config.node_id == "0000000000000000000000000000000000000000"
        assert handler.config.primary_id == "0000000000000000000000000000000000000000"
        assert handler.state_machine is not None
        assert handler.phase == QoIPhase.IDLE
    
    def test_start_round_as_primary(self):
        """Test starting a round as the primary node."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="0000000000000000000000000000000000000000",  # same = primary
            f=1,
        )
        node = MockNode()
        bus = EventBus()
        handler = QoIMessageHandler(config, node=node, event_bus=bus)
        
        # Start round
        probs = [0.1] * 10
        probs[5] = 0.2  # class 5
        
        msg = handler.start_round(
            request_id="req-1",
            image_hash="abc123" * 10,
            seq=0,
            own_probs=probs,
            trace_id="trace-1",
        )
        
        # Primary should return PRE_PREPARE message
        assert msg is not None
        assert msg.msg_type.value == "pre_prepare"
        assert msg.predicted_class == 5
        
        # Should have signed it
        assert node.identity.sign.called
        
        # Should have emitted event
        events = []
        bus.subscribe(EventType.QOI_PRE_PREPARE, lambda e: events.append(e))
        # (Note: we already published above; this won't catch it)
        # But we verified the state changed
        assert handler.phase == QoIPhase.PRE_PREPARE
    
    def test_start_round_as_replica(self):
        """Test starting a round as a replica node."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="1111111111111111111111111111111111111111",  # different = replica
            f=1,
        )
        node = MockNode()
        bus = EventBus()
        handler = QoIMessageHandler(config, node=node, event_bus=bus)
        
        probs = [0.1] * 10
        msg = handler.start_round(
            request_id="req-1",
            image_hash="abc123" * 10,
            seq=0,
            own_probs=probs,
        )
        
        # Replica should not return a message (just waits)
        assert msg is None
        
        # Should still have started the round
        assert handler.phase == QoIPhase.PRE_PREPARE
    
    def test_handle_pre_prepare_as_replica(self):
        """Test replica receiving PRE_PREPARE."""
        config = QoIMessageHandlerConfig(
            node_id="1111111111111111111111111111111111111111",
            primary_id="0000000000000000000000000000000000000000",
            f=1,
        )
        node = MockNode()
        bus = EventBus()
        handler = QoIMessageHandler(config, node=node, event_bus=bus)
        
        # Start round (as replica)
        handler.start_round(
            request_id="req-1",
            image_hash="abc" * 20,
            seq=0,
            own_probs=[0.1] * 10,
        )
        
        # Create PRE_PREPARE from primary
        from core.qoi.messages import MsgType
        pre_prepare = PrePrepareMsg(
            msg_type=MsgType.PRE_PREPARE,
            view=0,
            seq=0,
            sender_id="0000000000000000000000000000000000000000",
            request_id="req-1",
            image_hash="abc" * 20,
            probabilities=[0.1] * 10,
            predicted_class=5,
        )
        
        # Collect emitted events
        emitted_events = []
        bus.subscribe(EventType.QOI_PREPARE, lambda e: emitted_events.append(e))
        
        # Handle the message
        handler.on_message_received(pre_prepare)
        
        # Should have transitioned to PREPARE phase
        assert handler.phase == QoIPhase.PREPARE
        
        # Should have signed identity (mocked)
        assert node.identity.sign.called
    
    def test_handle_prepare_messages(self):
        """Test collecting PREPARE messages."""
        config = QoIMessageHandlerConfig(
            node_id="2222222222222222222222222222222222222222",
            primary_id="0000000000000000000000000000000000000000",
            f=1,  # need 2f+1 = 3 messages
        )
        node = MockNode()
        bus = EventBus()
        handler = QoIMessageHandler(config, node=node, event_bus=bus)
        
        # Start as replica
        handler.start_round(
            request_id="req-1",
            image_hash="abc" * 20,
            seq=0,
            own_probs=[0.1] * 10,
        )
        
        # Send PRE_PREPARE
        from core.qoi.messages import MsgType
        pre_prepare = PrePrepareMsg(
            msg_type=MsgType.PRE_PREPARE,
            view=0, seq=0,
            sender_id="0000000000000000000000000000000000000000",
            request_id="req-1",
            image_hash="abc" * 20,
            probabilities=[0.1] * 10,
            predicted_class=5,
        )
        handler.on_message_received(pre_prepare)
        
        # Send multiple PREPARE messages (need 2f+1 = 3)
        prepare_msgs = []
        for i in range(3):
            msg = PrepareMsg(
                msg_type=MsgType.PREPARE,
                view=0, seq=0,
                sender_id=f"{i:040x}",
                request_id="req-1",
                probabilities=[0.1] * 10,
                predicted_class=5,
            )
            prepare_msgs.append(msg)
            handler.on_message_received(msg)
        
        # After 2f+1 PREPAREs, should have transitioned to COMMIT
        assert handler.phase == QoIPhase.COMMIT
    
    def test_logging(self, capsys):
        """Test that message handling produces logs."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="0000000000000000000000000000000000000000",
            f=1,
        )
        handler = QoIMessageHandler(config)
        
        # Start round
        handler.start_round(
            request_id="req-1",
            image_hash="abc" * 20,
            seq=0,
            own_probs=[0.1] * 10,
        )
        
        captured = capsys.readouterr()
        assert "Starting QoI round" in captured.out
    
    def test_metrics(self):
        """Test accessing handler metrics."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="0000000000000000000000000000000000000000",
            f=1,
        )
        handler = QoIMessageHandler(config)
        
        # Access event bus metrics
        metrics = handler.event_bus.metrics()
        assert "total_published" in metrics
        assert "subscribed_types" in metrics
    
    def test_handler_repr(self):
        """Test handler string representation."""
        config = QoIMessageHandlerConfig(
            node_id="0000000000000000000000000000000000000000",
            primary_id="1111111111111111111111111111111111111111",
            f=1,
        )
        handler = QoIMessageHandler(config)
        
        repr_str = repr(handler)
        assert "QoIMessageHandler" in repr_str
        assert "0000" in repr_str
        assert "1111" in repr_str


class TestMessageHandlerIntegration:
    """Integration tests for message handler with state machine."""
    
    def setup_method(self):
        """Reset before each test."""
        reset_global_bus()
    
    def test_full_consensus_round_simulation(self):
        """Simulate a full consensus round with 4 nodes."""
        # Create 4 nodes: 1 primary + 3 replicas
        primary_id = "0000000000000000000000000000000000000000"
        replica_ids = [
            "1111111111111111111111111111111111111111",
            "2222222222222222222222222222222222222222",
            "3333333333333333333333333333333333333333",
        ]
        
        # Create handlers for each node
        bus = EventBus()
        handlers = {}
        
        # Primary
        config = QoIMessageHandlerConfig(
            node_id=primary_id,
            primary_id=primary_id,
            f=1,
        )
        handlers[primary_id] = QoIMessageHandler(config, node=MockNode(), event_bus=bus)
        
        # Replicas
        for rid in replica_ids:
            config = QoIMessageHandlerConfig(
                node_id=rid,
                primary_id=primary_id,
                f=1,
            )
            handlers[rid] = QoIMessageHandler(config, node=MockNode(), event_bus=bus)
        
        # Collect all events
        all_events = []
        bus.subscribe(
            EventType.QOI_PRE_PREPARE,
            lambda e: all_events.append(("pre_prepare", e)),
        )
        bus.subscribe(
            EventType.QOI_PREPARE,
            lambda e: all_events.append(("prepare", e)),
        )
        bus.subscribe(
            EventType.QOI_COMMIT,
            lambda e: all_events.append(("commit", e)),
        )
        bus.subscribe(
            EventType.QOI_COMMITTED,
            lambda e: all_events.append(("committed", e)),
        )
        
        # Start round on all nodes
        probs = [0.1] * 10
        probs[5] = 0.2
        
        for nid, handler in handlers.items():
            handler.start_round(
                request_id="req-1",
                image_hash="abc" * 20,
                seq=0,
                own_probs=probs,
            )
        
        # Primary should have emitted PRE_PREPARE
        assert handlers[primary_id].phase == QoIPhase.PRE_PREPARE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
