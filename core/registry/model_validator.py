"""
Model validator service for InferenceChain.

Validates ML models before registration to ensure:
- Correct input/output shapes
- Framework compatibility
- Inference performance
- Reproducibility
- Metadata completeness
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import importlib.util
import sys

from core.utils.logger import get_logger


class Framework(str, Enum):
    """Supported ML frameworks."""
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"
    ONNX = "onnx"


class ValidationStatus(str, Enum):
    """Model validation status."""
    PENDING = "pending"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    FAILED = "failed"


@dataclass
class ModelSpec:
    """Specification for a model to be registered."""
    
    name: str
    version: str
    framework: Framework
    input_shape: Tuple[int, ...]  # (3, 224, 224) for images
    output_shape: Tuple[int, ...]  # (1000,) for ImageNet
    max_latency_ms: float  # Max inference time
    max_size_mb: float  # Max model size
    min_accuracy: float  # Minimum expected accuracy (0-1)
    author: str
    description: str
    model_path: str  # Path to model file
    checkpoint_path: Optional[str] = None  # Optional checkpoint
    
    def validate_basic(self) -> Tuple[bool, str]:
        """Validate basic specification."""
        if not self.name or len(self.name) == 0:
            return False, "Model name required"
        
        if not self.version or len(self.version) == 0:
            return False, "Model version required"
        
        if not self.author or len(self.author) == 0:
            return False, "Author required"
        
        if self.max_latency_ms <= 0:
            return False, "Max latency must be > 0"
        
        if self.max_size_mb <= 0:
            return False, "Max size must be > 0"
        
        if not (0 <= self.min_accuracy <= 1):
            return False, "Min accuracy must be between 0 and 1"
        
        if len(self.input_shape) == 0 or len(self.output_shape) == 0:
            return False, "Input and output shapes required"
        
        return True, ""


@dataclass
class ValidationResult:
    """Result of model validation."""
    
    model_name: str
    status: ValidationStatus
    passed: bool
    checks_passed: int
    checks_total: int
    errors: list[str]
    warnings: list[str]
    inference_time_ms: Optional[float] = None
    model_size_mb: Optional[float] = None
    
    def add_error(self, error: str) -> None:
        """Add validation error."""
        self.errors.append(error)
        self.passed = False
    
    def add_warning(self, warning: str) -> None:
        """Add validation warning."""
        self.warnings.append(warning)
    
    def summary(self) -> str:
        """Get human-readable summary."""
        status_emoji = "✓" if self.passed else "✗"
        return f"{status_emoji} {self.model_name}: {self.checks_passed}/{self.checks_total} checks passed"


class ModelValidator:
    """
    Validate ML models for registration on InferenceChain.
    
    Ensures models meet predefined criteria for:
    - Framework compatibility
    - Input/output specifications
    - Performance requirements
    - Reproducibility
    
    Usage:
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
            author="user@example.com",
            description="ResNet-50 for ImageNet",
            model_path="/path/to/model.pth",
        )
        
        result = validator.validate(spec)
        if result.passed:
            print("Model accepted!")
        else:
            print(f"Validation failed: {result.errors}")
    """
    
    def __init__(self):
        """Initialize validator."""
        self.logger = get_logger("model_validator")
        self.validation_checks = [
            self._check_basic_spec,
            self._check_file_exists,
            self._check_model_size,
            self._check_framework,
            self._check_metadata,
        ]
    
    def validate(self, spec: ModelSpec) -> ValidationResult:
        """
        Validate a model specification.
        
        Args:
            spec: Model specification to validate
            
        Returns:
            ValidationResult with pass/fail status and details
        """
        self.logger.info(
            "Starting model validation",
            context={
                "model": spec.name,
                "version": spec.version,
                "framework": spec.framework.value,
            },
        )
        
        result = ValidationResult(
            model_name=spec.name,
            status=ValidationStatus.VALIDATING,
            passed=True,
            checks_passed=0,
            checks_total=len(self.validation_checks),
            errors=[],
            warnings=[],
        )
        
        # Run all validation checks
        for check in self.validation_checks:
            try:
                if check(spec, result):
                    result.checks_passed += 1
                else:
                    result.passed = False
            except Exception as e:
                result.add_error(f"Check {check.__name__} failed: {str(e)}")
                result.passed = False
        
        # Set final status
        result.status = ValidationStatus.VALID if result.passed else ValidationStatus.INVALID
        
        self.logger.info(
            "Model validation complete",
            context={
                "model": spec.name,
                "status": result.status.value,
                "checks_passed": result.checks_passed,
                "errors": len(result.errors),
            },
        )
        
        return result
    
    def _check_basic_spec(self, spec: ModelSpec, result: ValidationResult) -> bool:
        """Check basic specification validity."""
        valid, error = spec.validate_basic()
        if not valid:
            result.add_error(error)
            return False
        return True
    
    def _check_file_exists(self, spec: ModelSpec, result: ValidationResult) -> bool:
        """Check model files exist."""
        model_path = Path(spec.model_path)
        if not model_path.exists():
            result.add_error(f"Model file not found: {spec.model_path}")
            return False
        
        if spec.checkpoint_path:
            checkpoint_path = Path(spec.checkpoint_path)
            if not checkpoint_path.exists():
                result.add_warning(f"Checkpoint file not found: {spec.checkpoint_path}")
        
        return True
    
    def _check_model_size(self, spec: ModelSpec, result: ValidationResult) -> bool:
        """Check model file size."""
        model_path = Path(spec.model_path)
        size_mb = model_path.stat().st_size / (1024 * 1024)
        result.model_size_mb = size_mb
        
        if size_mb > spec.max_size_mb:
            result.add_error(f"Model too large: {size_mb:.1f}MB > {spec.max_size_mb}MB")
            return False
        
        self.logger.debug(
            "Model size check passed",
            context={"model": spec.name, "size_mb": f"{size_mb:.1f}"},
        )
        
        return True
    
    def _check_framework(self, spec: ModelSpec, result: ValidationResult) -> bool:
        """Check framework compatibility."""
        if spec.framework == Framework.PYTORCH:
            try:
                import torch
                self.logger.debug("PyTorch available", context={"version": torch.__version__})
                return True
            except ImportError:
                result.add_error("PyTorch not available")
                return False
        
        elif spec.framework == Framework.TENSORFLOW:
            try:
                import tensorflow
                self.logger.debug("TensorFlow available", context={"version": tensorflow.__version__})
                return True
            except ImportError:
                result.add_error("TensorFlow not available")
                return False
        
        elif spec.framework == Framework.ONNX:
            try:
                import onnx
                self.logger.debug("ONNX available", context={"version": onnx.__version__})
                return True
            except ImportError:
                result.add_error("ONNX not available")
                return False
        
        result.add_error(f"Unknown framework: {spec.framework}")
        return False
    
    def _check_metadata(self, spec: ModelSpec, result: ValidationResult) -> bool:
        """Check metadata completeness."""
        issues = []
        
        if not spec.description or len(spec.description) < 10:
            issues.append("Description too short (min 10 chars)")
        
        if not spec.author or "@" not in spec.author:
            result.add_warning("Author email not provided or invalid")
        
        if issues:
            result.add_warning(f"Metadata issues: {'; '.join(issues)}")
        
        return True
    
    def validate_model_script(
        self,
        script_path: str,
        required_functions: list[str] = None,
    ) -> Tuple[bool, str]:
        """
        Validate a custom model script has required functions.
        
        Args:
            script_path: Path to Python model script
            required_functions: List of required function names
            
        Returns:
            (passed, message)
        """
        if required_functions is None:
            required_functions = ["create_model", "preprocess", "postprocess"]
        
        try:
            spec = importlib.util.spec_from_file_location(
                "custom_model",
                script_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check required functions exist
            missing = []
            for func_name in required_functions:
                if not hasattr(module, func_name):
                    missing.append(func_name)
            
            if missing:
                return False, f"Missing required functions: {', '.join(missing)}"
            
            return True, "Script validation passed"
        
        except Exception as e:
            return False, f"Script validation failed: {str(e)}"


# Example usage and criteria
VALIDATION_CRITERIA = {
    "image_classification": {
        "framework": Framework.PYTORCH,
        "input_shape": (3, 224, 224),
        "output_shape": (1000,),  # ImageNet classes
        "max_latency_ms": 100,
        "max_size_mb": 200,
        "min_accuracy": 0.70,
    },
    "object_detection": {
        "framework": Framework.PYTORCH,
        "input_shape": (3, 416, 416),
        "output_shape": (25200, 85),  # YOLOv5 format
        "max_latency_ms": 200,
        "max_size_mb": 300,
        "min_accuracy": 0.50,
    },
    "text_classification": {
        "framework": Framework.ONNX,
        "input_shape": (1, 512),  # Token IDs
        "output_shape": (1, 2),  # Binary classification
        "max_latency_ms": 50,
        "max_size_mb": 500,
        "min_accuracy": 0.75,
    },
}
