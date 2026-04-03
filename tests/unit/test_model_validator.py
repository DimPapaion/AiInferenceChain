"""Tests for model_validator module."""

import pytest
from pathlib import Path
from core.registry.model_validator import (
    ModelValidator,
    ModelSpec,
    ValidationStatus,
    ValidationResult,
    Framework,
    VALIDATION_CRITERIA,
)


class TestModelSpec:
    """Tests for ModelSpec."""
    
    def test_valid_spec(self):
        """Test valid model spec."""
        spec = ModelSpec(
            name="resnet50",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,
            min_accuracy=0.75,
            author="test@example.com",
            description="ResNet-50 model",
            model_path="/tmp/model.pth",
        )
        valid, error = spec.validate_basic()
        assert valid
        assert error == ""
    
    def test_missing_name(self):
        """Test spec with missing name."""
        spec = ModelSpec(
            name="",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,
            min_accuracy=0.75,
            author="test@example.com",
            description="Model",
            model_path="/tmp/model.pth",
        )
        valid, error = spec.validate_basic()
        assert not valid
        assert "name" in error.lower()
    
    def test_invalid_latency(self):
        """Test spec with invalid latency."""
        spec = ModelSpec(
            name="model",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=-10,
            max_size_mb=200,
            min_accuracy=0.75,
            author="test@example.com",
            description="Model",
            model_path="/tmp/model.pth",
        )
        valid, error = spec.validate_basic()
        assert not valid
        assert "latency" in error.lower()
    
    def test_invalid_accuracy(self):
        """Test spec with invalid accuracy range."""
        spec = ModelSpec(
            name="model",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,
            min_accuracy=2.0,
            author="test@example.com",
            description="Model",
            model_path="/tmp/model.pth",
        )
        valid, error = spec.validate_basic()
        assert not valid
        assert "accuracy" in error.lower()


class TestModelValidator:
    """Tests for ModelValidator."""
    
    def test_validator_initialization(self):
        """Test validator initializes correctly."""
        validator = ModelValidator()
        assert validator is not None
        assert len(validator.validation_checks) == 5
    
    def test_validate_missing_file(self):
        """Test validation fails when file missing."""
        validator = ModelValidator()
        spec = ModelSpec(
            name="resnet50",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,
            min_accuracy=0.75,
            author="test@example.com",
            description="ResNet-50 model",
            model_path="/nonexistent/path/model.pth",
        )
        
        result = validator.validate(spec)
        assert not result.passed
        assert result.status == ValidationStatus.INVALID
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()
    
    def test_validate_with_existing_file(self, tmp_path):
        """Test validation with existing file."""
        # Create temporary model file
        model_file = tmp_path / "model.pth"
        model_file.write_text("dummy model data")
        
        validator = ModelValidator()
        spec = ModelSpec(
            name="resnet50",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,
            min_accuracy=0.75,
            author="test@example.com",
            description="ResNet-50 model",
            model_path=str(model_file),
        )
        
        result = validator.validate(spec)
        # Should pass basic checks except framework (PyTorch may not be installed)
        # But file should exist
        assert result.model_size_mb is not None
        assert result.checks_passed >= 1  # At least basic spec check
    
    def test_validate_model_size_exceeded(self, tmp_path):
        """Test validation fails when model too large."""
        # Create large temporary file
        model_file = tmp_path / "large_model.pth"
        model_file.write_bytes(b"x" * (300 * 1024 * 1024))  # 300MB
        
        validator = ModelValidator()
        spec = ModelSpec(
            name="large_model",
            version="1.0",
            framework=Framework.PYTORCH,
            input_shape=(3, 224, 224),
            output_shape=(1000,),
            max_latency_ms=100,
            max_size_mb=200,  # Only allow 200MB
            min_accuracy=0.75,
            author="test@example.com",
            description="Large model",
            model_path=str(model_file),
        )
        
        result = validator.validate(spec)
        assert not result.passed
        assert any("too large" in e.lower() for e in result.errors)
    
    def test_validation_result_summary(self):
        """Test validation result summary generation."""
        result = ValidationResult(
            model_name="test_model",
            status=ValidationStatus.VALID,
            passed=True,
            checks_passed=5,
            checks_total=5,
            errors=[],
            warnings=[],
        )
        
        summary = result.summary()
        assert "test_model" in summary
        assert "5/5" in summary
        assert "✓" in summary
    
    def test_validation_result_failed_summary(self):
        """Test failed validation result summary."""
        result = ValidationResult(
            model_name="bad_model",
            status=ValidationStatus.INVALID,
            passed=False,
            checks_passed=2,
            checks_total=5,
            errors=["Error 1"],
            warnings=[],
        )
        
        summary = result.summary()
        assert "bad_model" in summary
        assert "2/5" in summary
        assert "✗" in summary


class TestValidationCriteria:
    """Tests for validation criteria."""
    
    def test_image_classification_criteria(self):
        """Test image classification criteria exists and is correct."""
        assert "image_classification" in VALIDATION_CRITERIA
        criteria = VALIDATION_CRITERIA["image_classification"]
        
        assert criteria["framework"] == Framework.PYTORCH
        assert criteria["input_shape"] == (3, 224, 224)
        assert criteria["output_shape"] == (1000,)
        assert criteria["min_accuracy"] >= 0.5
    
    def test_object_detection_criteria(self):
        """Test object detection criteria exists."""
        assert "object_detection" in VALIDATION_CRITERIA
        criteria = VALIDATION_CRITERIA["object_detection"]
        
        assert criteria["framework"] == Framework.PYTORCH
        assert criteria["input_shape"] == (3, 416, 416)
    
    def test_text_classification_criteria(self):
        """Test text classification criteria exists."""
        assert "text_classification" in VALIDATION_CRITERIA
        criteria = VALIDATION_CRITERIA["text_classification"]
        
        assert criteria["framework"] == Framework.ONNX
        assert criteria["input_shape"] == (1, 512)

