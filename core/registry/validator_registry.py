"""
Validator registration and staking system for InferenceChain.

Manages:
- Validator registration with stake requirements
- Stake threshold enforcement
- Validator status and lifecycle
- Rewards and penalties
- Validator discovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Set
from datetime import datetime
from uuid import uuid4
import json

from core.utils.logger import get_logger


class ValidatorStatus(str, Enum):
    """Validator lifecycle status."""
    PENDING = "pending"  # Waiting for stake confirmation
    ACTIVE = "active"    # Fully operational
    INACTIVE = "inactive"  # Temporarily offline
    SLASHED = "slashed"  # Penalized for misbehavior
    EXITING = "exiting"  # Unstaking in progress


@dataclass
class ValidatorStake:
    """Record of a validator's stake."""
    
    amount: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tx_hash: Optional[str] = None
    confirmed: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "amount": self.amount,
            "timestamp": self.timestamp.isoformat(),
            "tx_hash": self.tx_hash,
            "confirmed": self.confirmed,
        }


@dataclass
class ValidatorInfo:
    """Information about a registered validator."""
    
    validator_id: str
    address: str  # Node address/public key
    name: str
    email: str
    stake: float  # Total staked amount
    status: ValidatorStatus
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    models_validated: int = 0
    blocks_proposed: int = 0
    slashes_received: int = 0
    rewards_earned: float = 0.0
    penalties_paid: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "validator_id": self.validator_id,
            "address": self.address,
            "name": self.name,
            "email": self.email,
            "stake": self.stake,
            "status": self.status.value,
            "joined_at": self.joined_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "models_validated": self.models_validated,
            "blocks_proposed": self.blocks_proposed,
            "slashes_received": self.slashes_received,
            "rewards_earned": self.rewards_earned,
            "penalties_paid": self.penalties_paid,
            "metadata": self.metadata,
        }
    
    def update_heartbeat(self) -> None:
        """Update last heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow()


@dataclass
class RegistrationRequest:
    """Request to register a new validator."""
    
    address: str
    name: str
    email: str
    stake_amount: float
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def validate(self, min_stake: float) -> tuple[bool, str]:
        """Validate registration request."""
        if not self.address or len(self.address) == 0:
            return False, "Address required"
        
        if not self.name or len(self.name) == 0:
            return False, "Name required"
        
        if not self.email or "@" not in self.email:
            return False, "Valid email required"
        
        if self.stake_amount < min_stake:
            return False, f"Stake must be >= {min_stake}"
        
        return True, ""


class ValidatorRegistry:
    """
    Registry for managing validators in InferenceChain.
    
    Features:
    - Validator registration with stake verification
    - Stake threshold enforcement
    - Validator status tracking
    - Rewards and penalties
    - Validator discovery
    
    Usage:
        registry = ValidatorRegistry(min_stake=32.0)
        
        # Register validator
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        result = registry.register_validator(req)
        
        # Activate validator after stake confirmation
        registry.confirm_stake(result.validator_id)
        
        # Query validators
        active = registry.get_active_validators()
    """
    
    def __init__(self, min_stake: float = 32.0):
        """
        Initialize validator registry.
        
        Args:
            min_stake: Minimum stake amount required to become validator (default: 32.0,
                      like Ethereum 2.0)
        """
        self.logger = get_logger("validator_registry")
        self.min_stake = min_stake
        
        # Storage: validator_id -> ValidatorInfo
        self.validators: Dict[str, ValidatorInfo] = {}
        
        # Storage: address -> validator_id (for quick lookup)
        self.address_index: Dict[str, str] = {}
        
        # Storage: validator_id -> List[ValidatorStake]
        self.stake_history: Dict[str, List[ValidatorStake]] = {}
        
        self.logger.info(
            "ValidatorRegistry initialized",
            context={"min_stake": min_stake},
        )
    
    def register_validator(
        self,
        request: RegistrationRequest,
    ) -> ValidatorInfo:
        """
        Register a new validator.
        
        Args:
            request: Registration request
            
        Returns:
            ValidatorInfo for newly registered validator
            
        Raises:
            ValueError: If validation fails or validator already exists
        """
        # Validate request
        valid, error = request.validate(self.min_stake)
        if not valid:
            raise ValueError(f"Invalid registration request: {error}")
        
        # Check address not already registered
        if request.address in self.address_index:
            raise ValueError(f"Address already registered: {request.address}")
        
        # Create validator
        validator_id = str(uuid4())
        validator = ValidatorInfo(
            validator_id=validator_id,
            address=request.address,
            name=request.name,
            email=request.email,
            stake=request.stake_amount,
            status=ValidatorStatus.PENDING,
            metadata=request.metadata,
        )
        
        # Store validator and create index
        self.validators[validator_id] = validator
        self.address_index[request.address] = validator_id
        self.stake_history[validator_id] = [
            ValidatorStake(
                amount=request.stake_amount,
                confirmed=False,
            )
        ]
        
        self.logger.info(
            "Validator registered",
            context={
                "validator_id": validator_id,
                "address": request.address,
                "stake": request.stake_amount,
                "status": ValidatorStatus.PENDING.value,
            },
        )
        
        return validator
    
    def confirm_stake(self, validator_id: str, tx_hash: str = None) -> ValidatorInfo:
        """
        Confirm stake for pending validator.
        
        Args:
            validator_id: Validator ID
            tx_hash: Optional transaction hash for audit trail
            
        Returns:
            Updated ValidatorInfo
            
        Raises:
            ValueError: If validator not found or not pending
        """
        validator = self.validators.get(validator_id)
        if not validator:
            raise ValueError(f"Validator not found: {validator_id}")
        
        if validator.status != ValidatorStatus.PENDING:
            raise ValueError(
                f"Validator not pending: {validator_id} (status={validator.status.value})"
            )
        
        # Mark stake as confirmed
        latest_stake = self.stake_history[validator_id][-1]
        latest_stake.confirmed = True
        latest_stake.tx_hash = tx_hash
        
        # Activate validator
        validator.status = ValidatorStatus.ACTIVE
        validator.update_heartbeat()
        
        self.logger.info(
            "Validator stake confirmed",
            context={
                "validator_id": validator_id,
                "tx_hash": tx_hash or "none",
                "status": ValidatorStatus.ACTIVE.value,
            },
        )
        
        return validator
    
    def get_validator(self, validator_id: str) -> Optional[ValidatorInfo]:
        """Get validator by ID."""
        return self.validators.get(validator_id)
    
    def get_validator_by_address(self, address: str) -> Optional[ValidatorInfo]:
        """Get validator by address."""
        validator_id = self.address_index.get(address)
        if validator_id:
            return self.validators.get(validator_id)
        return None
    
    def get_active_validators(self) -> List[ValidatorInfo]:
        """Get all active validators."""
        return [
            v for v in self.validators.values()
            if v.status == ValidatorStatus.ACTIVE
        ]
    
    def get_validators_by_status(self, status: ValidatorStatus) -> List[ValidatorInfo]:
        """Get validators by status."""
        return [v for v in self.validators.values() if v.status == status]
    
    def get_validator_count(self, status: ValidatorStatus = None) -> int:
        """Get validator count, optionally filtered by status."""
        if status is None:
            return len(self.validators)
        return len(self.get_validators_by_status(status))
    
    def get_total_stake(self) -> float:
        """Get total stake across all validators."""
        return sum(v.stake for v in self.validators.values())
    
    def get_active_stake(self) -> float:
        """Get total active stake."""
        return sum(v.stake for v in self.get_active_validators())
    
    def update_heartbeat(self, validator_id: str) -> Optional[ValidatorInfo]:
        """Update validator heartbeat (keep-alive signal)."""
        validator = self.validators.get(validator_id)
        if validator:
            validator.update_heartbeat()
        return validator
    
    def increment_models_validated(self, validator_id: str) -> None:
        """Increment model validation count."""
        validator = self.validators.get(validator_id)
        if validator:
            validator.models_validated += 1
    
    def increment_blocks_proposed(self, validator_id: str) -> None:
        """Increment blocks proposed count."""
        validator = self.validators.get(validator_id)
        if validator:
            validator.blocks_proposed += 1
    
    def add_reward(self, validator_id: str, amount: float) -> None:
        """Add reward to validator."""
        validator = self.validators.get(validator_id)
        if validator:
            validator.rewards_earned += amount
            self.logger.debug(
                "Reward added",
                context={
                    "validator_id": validator_id,
                    "amount": amount,
                },
            )
    
    def slash_validator(
        self,
        validator_id: str,
        amount: float,
        reason: str = "",
    ) -> Optional[ValidatorInfo]:
        """
        Slash validator stake for misbehavior.
        
        Args:
            validator_id: Validator ID
            amount: Amount to slash
            reason: Reason for slash
            
        Returns:
            Updated ValidatorInfo or None if not found
        """
        validator = self.validators.get(validator_id)
        if not validator:
            return None
        
        # Apply slash (reduce stake and mark penalties)
        slash_amount = min(amount, validator.stake)
        validator.stake -= slash_amount
        validator.penalties_paid += slash_amount
        validator.slashes_received += 1
        
        # If stake falls below minimum, mark as inactive
        if validator.stake < self.min_stake:
            validator.status = ValidatorStatus.SLASHED
        
        self.logger.warn(
            "Validator slashed",
            context={
                "validator_id": validator_id,
                "slash_amount": slash_amount,
                "remaining_stake": validator.stake,
                "reason": reason,
            },
        )
        
        return validator
    
    def deactivate_validator(self, validator_id: str, reason: str = "") -> Optional[ValidatorInfo]:
        """Deactivate validator temporarily."""
        validator = self.validators.get(validator_id)
        if validator:
            validator.status = ValidatorStatus.INACTIVE
            self.logger.info(
                "Validator deactivated",
                context={
                    "validator_id": validator_id,
                    "reason": reason,
                },
            )
        return validator
    
    def reactivate_validator(self, validator_id: str) -> Optional[ValidatorInfo]:
        """Reactivate deactivated validator."""
        validator = self.validators.get(validator_id)
        if validator and validator.status == ValidatorStatus.INACTIVE:
            validator.status = ValidatorStatus.ACTIVE
            validator.update_heartbeat()
            self.logger.info(
                "Validator reactivated",
                context={"validator_id": validator_id},
            )
        return validator
    
    def list_validators(self, limit: int = None) -> List[ValidatorInfo]:
        """List validators, optionally limited."""
        validators = list(self.validators.values())
        if limit:
            return validators[:limit]
        return validators
    
    def export_state(self) -> dict:
        """Export registry state for persistence."""
        return {
            "min_stake": self.min_stake,
            "validators": {
                vid: v.to_dict()
                for vid, v in self.validators.items()
            },
            "stake_history": {
                vid: [s.to_dict() for s in stakes]
                for vid, stakes in self.stake_history.items()
            },
        }
    
    def import_state(self, state: dict) -> None:
        """Import registry state from persistence."""
        self.min_stake = state.get("min_stake", self.min_stake)
        
        # Restore validators
        for vid, v_dict in state.get("validators", {}).items():
            validator = ValidatorInfo(
                validator_id=v_dict["validator_id"],
                address=v_dict["address"],
                name=v_dict["name"],
                email=v_dict["email"],
                stake=v_dict["stake"],
                status=ValidatorStatus(v_dict["status"]),
                joined_at=datetime.fromisoformat(v_dict["joined_at"]),
                last_heartbeat=(
                    datetime.fromisoformat(v_dict["last_heartbeat"])
                    if v_dict["last_heartbeat"]
                    else None
                ),
                models_validated=v_dict["models_validated"],
                blocks_proposed=v_dict["blocks_proposed"],
                slashes_received=v_dict["slashes_received"],
                rewards_earned=v_dict["rewards_earned"],
                penalties_paid=v_dict["penalties_paid"],
                metadata=v_dict["metadata"],
            )
            self.validators[vid] = validator
            self.address_index[validator.address] = vid
