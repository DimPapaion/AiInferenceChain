"""
InferenceChain registry module.

Provides:
- Model validation (ModelValidator, ModelSpec)
- Validator registration and staking (ValidatorRegistry, ValidatorInfo)
- Model registry database (ModelRegistry)
"""

from .model_validator import (
    ModelValidator,
    ModelSpec,
    ValidationResult,
    ValidationStatus,
    Framework,
    VALIDATION_CRITERIA,
)

from .validator_registry import (
    ValidatorRegistry,
    ValidatorInfo,
    ValidatorStatus,
    RegistrationRequest,
    ValidatorStake,
)

from .model_registry import (
    ModelRegistry,
    ModelState,
    ModelValidationRecord,
    ModelBenchmark,
)

__all__ = [
    # Model Validator
    "ModelValidator",
    "ModelSpec",
    "ValidationResult",
    "ValidationStatus",
    "Framework",
    "VALIDATION_CRITERIA",
    # Validator Registry
    "ValidatorRegistry",
    "ValidatorInfo",
    "ValidatorStatus",
    "RegistrationRequest",
    "ValidatorStake",
    # Model Registry
    "ModelRegistry",
    "ModelState",
    "ModelValidationRecord",
    "ModelBenchmark",
]
