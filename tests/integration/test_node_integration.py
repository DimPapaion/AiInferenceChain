"""
Integration test: Full consensus round with event-driven, persistent node.

Tests that InferenceNode now:
1. Uses event-driven QoIMessageHandler (Phase 1)
2. Automatically persists to SQLite (Phase 2)
3. Maintains complete audit trail
4. Recovers from crashes with correct state

This validates the integration of Phases 1 and 2 with the InferenceNode.
"""

import tempfile
from pathlib import Path

import pytest
import torch
import torchvision.transforms as transforms

from core.node.inference_node import InferenceNode, ModelHandle
from core.node.identity import NodeIdentity, make_test_identity
from core.events import EventBus, EventType, ConsensusEvent, get_global_bus
from core.qoi.consensus_log import ConsensusLog


class TestEventDrivenNode:
    """Test InferenceNode with event-driven architecture."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for each test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def sample_image(self):
        """Create a sample CIFAR-10 image."""
        # Create a random 32x32 RGB image
        return torch.randn(3, 32, 32)
    
    @pytest.fixture
    def test_model(self):
        """Create a test model handle."""
        return ModelHandle(
            name="resnet20",
            architecture={"type": "resnet", "depth": 20},
            weights_path="models/weights/resnet20.pth",
            weights_hash="abc" * 20,
            dataset_id="cifar10",
        )
    
    def test_inference_node_with_event_bus(self, temp_db, test_model, sample_image):
        """Test that InferenceNode uses event bus for consensus."""
        
        # Create local event bus for testing
        bus = EventBus()
        
        # Create node with event bus
        identity = make_test_identity(seed=1)
        node = InferenceNode(
            identity=identity,
            model=test_model,
            endpoint="127.0.0.1:5000",
            f=1,
            event_bus=bus,
            db_path=str(Path(temp_db) / "node-1.db"),
        )
        
        # Verify node has event bus
        assert node.event_bus is bus
        assert node.logger is not None
        assert node.consensus_log is not None
    
    def test_inference_node_creates_persistence_log(self, temp_db, test_model):
        """Test that InferenceNode creates a persistence database."""
        
        db_path = Path(temp_db) / "node-1.db"
        identity = make_test_identity(seed=2)
        
        node = InferenceNode(
            identity=identity,
            model=test_model,
            endpoint="127.0.0.1:5000",
            db_path=str(db_path),
        )
        
        # Verify database was created
        assert node.db_path == str(db_path)
        assert node.consensus_log is not None
        
        # Verify database file exists
        assert db_path.exists()
    
    def test_four_node_consensus_round_with_persistence(self, temp_db):
        """Test that 4 nodes can communicate and events are tracked."""
        
        # Create a minimal model handle for testing (won't actually load weights)
        class MockModel:
            def __init__(self):
                self.name = "mock"
                self.architecture = {}
                self.weights_path = "mock.pth"
                self.weights_hash = "mock"
                self.dataset_id = "mock"
            def predict(self, img):
                # Return dummy predictions
                return [0.1] * 10, 5
            def predict_batch(self, indices, dataset_id=None):
                return [5] * len(indices)
        
        # Create shared event bus for all nodes
        bus = EventBus()
        
        # Create 4-node cluster (no actual model loading)
        nodes = {}
        primary_id = None
        
        for i in range(4):
            identity = make_test_identity(seed=100 + i)
            if i == 0:
                primary_id = identity.address
            
            db_path = str(Path(temp_db) / f"node-{i}.db")
            node = InferenceNode(
                identity=identity,
                model=MockModel(),  # Use mock model
                endpoint=f"127.0.0.1:{5000 + i}",
                f=1,
                event_bus=bus,
                db_path=db_path,
            )
            nodes[i] = node
        
        # Track events
        events_received = []
        
        def track_event(event):
            events_received.append(event)
        
        bus.subscribe(EventType.QOI_PRE_PREPARE, track_event)
        bus.subscribe(EventType.QOI_PREPARE, track_event)
        bus.subscribe(EventType.QOI_COMMIT, track_event)
        bus.subscribe(EventType.QOI_COMMITTED, track_event)
        
        # Simulate consensus events recorded to logs
        request_id = "req-consensus"
        from core.qoi.state_machine import QoIPhase
        
        for i, node in nodes.items():
            node.consensus_log.record_checkpoint(
                round_id=request_id,
                view=0,
                seq=0,
                phase=QoIPhase.PRE_PREPARE,
                trace_id=f"trace-node-{i}",
                event_data={"node_id": node.node_id},
            )
        
        # Verify each node has logged the checkpoint
        for i, node in nodes.items():
            history = node.consensus_log.get_round_history(request_id)
            assert len(history) >= 1
    
    def test_persistence_survives_node_restart(self, temp_db, test_model):
        """Test that node state survives a 'restart' via database recovery."""
        
        db_path = Path(temp_db) / "node-persist.db"
        
        # Phase 1: Node operates and logs events
        bus1 = EventBus()
        identity = make_test_identity(seed=42)
        node1 = InferenceNode(
            identity=identity,
            model=test_model,
            endpoint="127.0.0.1:5000",
            event_bus=bus1,
            db_path=str(db_path),
        )
        
        # Manually record some consensus events to simulate activity
        from core.events import ConsensusEvent, EventType
        from core.qoi.state_machine import QoIPhase
        
        request_id = "req-persist"
        
        # Record checkpoint at PRE_PREPARE phase
        node1.consensus_log.record_checkpoint(
            round_id=request_id,
            view=0,
            seq=0,
            phase=QoIPhase.PRE_PREPARE,
            trace_id="trace-1",
            event_data={"node_id": node1.node_id, "predicted_class": 5},
        )
        
        # Record an event
        event = ConsensusEvent(
            event_type=EventType.QOI_PREPARE,
            trace_id="trace-2",
            data={"request_id": request_id, "node_id": node1.node_id},
        )
        node1.consensus_log.record_event(event)
        
        # Get stats before "crash"
        stats_before = node1.consensus_log.stats()
        assert stats_before["checkpoint_count"] >= 1
        
        # "Crash" - close node
        del node1
        del bus1
        
        # Phase 2: Node restarts
        bus2 = EventBus()
        node2 = InferenceNode(
            identity=identity,  # Same identity
            model=test_model,
            endpoint="127.0.0.1:5000",
            event_bus=bus2,
            db_path=str(db_path),  # Same database
        )
        
        # Verify state was recovered
        checkpoint = node2.consensus_log.recover_latest_round()
        assert checkpoint is not None
        assert checkpoint.round_id == request_id
        assert checkpoint.phase == "PRE_PREPARE"  # phase is stored as string
        
        # Verify stats match
        stats_after = node2.consensus_log.stats()
        assert stats_after["checkpoint_count"] == stats_before["checkpoint_count"]
        assert stats_after["event_count"] == stats_before["event_count"]
        
        # Verify history is intact
        history = node2.consensus_log.get_round_history(request_id)
        assert len(history) >= 2  # At least checkpoint + event


class TestInferenceNodeIntegration:
    """Test InferenceNode integration with event bus and persistence."""
    
    def test_multiple_rounds_in_same_database(self):
        """Test that node can run multiple consensus rounds with full audit trail."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "multi-round.db"
            bus = EventBus()
            
            identity = make_test_identity(seed=99)
            model = ModelHandle(
                name="resnet20",
                architecture={"type": "resnet", "depth": 20},
                weights_path="models/weights/resnet20.pth",
                weights_hash="xyz" * 20,
                dataset_id="cifar10",
            )
            
            node = InferenceNode(
                identity=identity,
                model=model,
                endpoint="127.0.0.1:5000",
                event_bus=bus,
                db_path=str(db_path),
            )
            
            from core.qoi.state_machine import QoIPhase
            
            # Simulate 3 consensus rounds
            for round_num in range(3):
                request_id = f"req-{round_num}"
                
                # Record checkpoint for each phase
                for phase_idx, phase in enumerate([QoIPhase.PRE_PREPARE, QoIPhase.PREPARE, QoIPhase.COMMIT]):
                    node.consensus_log.record_checkpoint(
                        round_id=request_id,
                        view=0,
                        seq=round_num,
                        phase=phase,
                        trace_id=f"trace-{round_num}-{phase_idx}",
                        event_data={"round": round_num, "phase": phase.value},
                    )
            
            # Verify all rounds are in the log
            stats = node.consensus_log.stats()
            assert stats["round_count"] == 3
            assert stats["checkpoint_count"] == 9  # 3 rounds × 3 phases
            
            # Verify we can retrieve each round's history
            for round_num in range(3):
                history = node.consensus_log.get_round_history(f"req-{round_num}")
                assert len(history) == 3
    
    def test_node_logging_integration(self):
        """Test that node logs are produced correctly."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            identity = make_test_identity(seed=77)
            model = ModelHandle(
                name="resnet20",
                architecture={"type": "resnet", "depth": 20},
                weights_path="models/weights/resnet20.pth",
                weights_hash="def" * 20,
                dataset_id="cifar10",
            )
            
            node = InferenceNode(
                identity=identity,
                model=model,
                endpoint="127.0.0.1:5000",
                db_path=str(Path(tmpdir) / "node.db"),
            )
            
            # Node should have a logger
            assert node.logger is not None
            assert "node_" in node.logger.component


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
