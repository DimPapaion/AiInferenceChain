"""Tests for model_registry module."""

import pytest
import tempfile
from pathlib import Path
from core.registry.model_registry import (
    ModelRegistry,
    ModelState,
)


class TestModelRegistry:
    """Tests for ModelRegistry."""
    
    @pytest.fixture
    def registry(self):
        """Create temporary registry for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            reg = ModelRegistry(str(db_path))
            reg.initialize()
            yield reg
            reg.close()
    
    def test_registry_initialization(self, registry):
        """Test registry initializes correctly."""
        assert registry.connection is not None
        assert registry.db_path.exists()
    
    def test_register_model(self, registry):
        """Test registering a model."""
        model_id = registry.register_model(
            model_id="resnet50_v1",
            name="ResNet-50",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            description="ResNet-50 for ImageNet",
            min_accuracy=0.75,
            max_latency_ms=100,
            max_size_mb=200,
            model_path="/models/resnet50.pth",
        )
        
        assert model_id == "resnet50_v1"
        
        # Verify model was stored
        model = registry.get_model(model_id)
        assert model is not None
        assert model["name"] == "ResNet-50"
        assert model["state"] == ModelState.DRAFT.value
    
    def test_get_model(self, registry):
        """Test retrieving a model."""
        registry.register_model(
            model_id="vgg16_v1",
            name="VGG-16",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/vgg16.pth",
        )
        
        model = registry.get_model("vgg16_v1")
        assert model is not None
        assert model["name"] == "VGG-16"
    
    def test_get_nonexistent_model(self, registry):
        """Test getting nonexistent model returns None."""
        model = registry.get_model("nonexistent")
        assert model is None
    
    def test_get_model_by_name_version(self, registry):
        """Test getting model by name and version."""
        registry.register_model(
            model_id="inception_v1",
            name="InceptionV3",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 299, 299]",
            output_shape="[1000]",
            model_path="/models/inception.pth",
        )
        
        model = registry.get_model_by_name_version("InceptionV3", "1.0.0")
        assert model is not None
        assert model["model_id"] == "inception_v1"
    
    def test_get_models_by_author(self, registry):
        """Test getting models by author."""
        author = "alice@example.com"
        
        for i in range(3):
            registry.register_model(
                model_id=f"model_{i}",
                name=f"Model {i}",
                author=author,
                version="1.0.0",
                framework="pytorch",
                input_shape="[3, 224, 224]",
                output_shape="[1000]",
                model_path=f"/models/model_{i}.pth",
            )
        
        models = registry.get_models_by_author(author)
        assert len(models) == 3
    
    def test_get_models_by_state(self, registry):
        """Test getting models by state."""
        # Register model
        model_id = registry.register_model(
            model_id="test_model",
            name="Test Model",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        # Should be in draft state initially
        drafts = registry.get_models_by_state(ModelState.DRAFT)
        assert len(drafts) == 1
        assert drafts[0]["model_id"] == model_id
        
        # Update state to approved
        registry.update_model_state(model_id, ModelState.APPROVED)
        
        drafts = registry.get_models_by_state(ModelState.DRAFT)
        assert len(drafts) == 0
        
        approved = registry.get_models_by_state(ModelState.APPROVED)
        assert len(approved) == 1
    
    def test_update_model_state(self, registry):
        """Test updating model state."""
        model_id = registry.register_model(
            model_id="state_model",
            name="State Model",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        model = registry.get_model(model_id)
        assert model["state"] == ModelState.DRAFT.value
        
        registry.update_model_state(model_id, ModelState.APPROVED)
        
        model = registry.get_model(model_id)
        assert model["state"] == ModelState.APPROVED.value
    
    def test_add_validation(self, registry):
        """Test adding validation record."""
        model_id = registry.register_model(
            model_id="val_model",
            name="Validation Test",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        validation_id = registry.add_validation(
            model_id=model_id,
            validator_id="validator1",
            passed=True,
            checks_passed=5,
            checks_total=5,
            errors=[],
            warnings=[],
        )
        
        assert validation_id is not None
        
        # Model should now be approved
        model = registry.get_model(model_id)
        assert model["state"] == ModelState.APPROVED.value
    
    def test_get_model_validations(self, registry):
        """Test retrieving validation history."""
        model_id = registry.register_model(
            model_id="multi_val_model",
            name="Multi Validation",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        # Add multiple validations
        for i in range(3):
            registry.add_validation(
                model_id=model_id,
                validator_id=f"validator{i}",
                passed=True,
                checks_passed=5,
                checks_total=5,
                errors=[],
                warnings=[],
            )
        
        validations = registry.get_model_validations(model_id)
        assert len(validations) == 3
    
    def test_add_failed_validation(self, registry):
        """Test adding failed validation."""
        model_id = registry.register_model(
            model_id="bad_model",
            name="Bad Model",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        validation_id = registry.add_validation(
            model_id=model_id,
            validator_id="validator1",
            passed=False,
            checks_passed=2,
            checks_total=5,
            errors=["Invalid input shape"],
            warnings=["Large file size"],
        )
        
        assert validation_id is not None
        
        # Model should still be in draft state
        model = registry.get_model(model_id)
        assert model["state"] != ModelState.APPROVED.value
    
    def test_add_benchmark(self, registry):
        """Test adding benchmark record."""
        model_id = registry.register_model(
            model_id="bench_model",
            name="Benchmark Model",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        benchmark_id = registry.add_benchmark(
            model_id=model_id,
            validator_id="validator1",
            inference_time_ms=45.2,
            accuracy=0.92,
        )
        
        assert benchmark_id is not None
    
    def test_get_model_benchmarks(self, registry):
        """Test retrieving benchmark history."""
        model_id = registry.register_model(
            model_id="multi_bench_model",
            name="Multi Benchmark",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        # Add multiple benchmarks
        for i in range(3):
            registry.add_benchmark(
                model_id=model_id,
                validator_id=f"validator{i}",
                inference_time_ms=40.0 + i,
                accuracy=0.90 + (i * 0.01),
            )
        
        benchmarks = registry.get_model_benchmarks(model_id)
        assert len(benchmarks) == 3
    
    def test_get_benchmark_stats(self, registry):
        """Test getting aggregate benchmark statistics."""
        model_id = registry.register_model(
            model_id="stats_model",
            name="Stats Model",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/test.pth",
        )
        
        # Add benchmarks
        registry.add_benchmark(model_id, "v1", 40.0, 0.90)
        registry.add_benchmark(model_id, "v2", 45.0, 0.92)
        registry.add_benchmark(model_id, "v3", 50.0, 0.91)
        
        stats = registry.get_benchmark_stats(model_id)
        
        assert stats["total_benchmarks"] == 3
        assert stats["avg_latency"] == pytest.approx(45.0)
        assert stats["min_latency"] == 40.0
        assert stats["max_latency"] == 50.0
    
    def test_list_models(self, registry):
        """Test listing models."""
        for i in range(5):
            registry.register_model(
                model_id=f"list_model_{i}",
                name=f"List Model {i}",
                author="test@example.com",
                version="1.0.0",
                framework="pytorch",
                input_shape="[3, 224, 224]",
                output_shape="[1000]",
                model_path=f"/models/model_{i}.pth",
            )
        
        all_models = registry.list_models()
        assert len(all_models) >= 5
        
        limited = registry.list_models(limit=3)
        assert len(limited) == 3
    
    def test_get_total_models(self, registry):
        """Test getting total model count."""
        for i in range(5):
            registry.register_model(
                model_id=f"count_model_{i}",
                name=f"Count Model {i}",
                author="test@example.com",
                version="1.0.0",
                framework="pytorch",
                input_shape="[3, 224, 224]",
                output_shape="[1000]",
                model_path=f"/models/model_{i}.pth",
            )
        
        count = registry.get_total_models()
        assert count >= 5
    
    def test_get_stats(self, registry):
        """Test getting registry statistics."""
        # Register models in different states
        m1 = registry.register_model(
            model_id="stat_model_1",
            name="Stat Model 1",
            author="test@example.com",
            version="1.0.0",
            framework="pytorch",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/m1.pth",
        )
        
        m2 = registry.register_model(
            model_id="stat_model_2",
            name="Stat Model 2",
            author="test@example.com",
            version="1.0.0",
            framework="tensorflow",
            input_shape="[3, 224, 224]",
            output_shape="[1000]",
            model_path="/models/m2.pth",
        )
        
        # Approve first model
        registry.update_model_state(m1, ModelState.APPROVED)
        
        stats = registry.get_stats()
        
        assert "total_models" in stats
        assert "by_state" in stats
        assert "by_framework" in stats
        assert stats["approved"] >= 1
