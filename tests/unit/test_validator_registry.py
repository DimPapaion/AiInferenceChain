"""Tests for validator_registry module."""

import pytest
from datetime import datetime, timedelta
import time
from core.registry.validator_registry import (
    ValidatorRegistry,
    ValidatorInfo,
    ValidatorStatus,
    RegistrationRequest,
)


class TestRegistrationRequest:
    """Tests for RegistrationRequest."""
    
    def test_valid_request(self):
        """Test valid registration request."""
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        valid, error = req.validate(min_stake=32.0)
        assert valid
        assert error == ""
    
    def test_missing_address(self):
        """Test request with missing address."""
        req = RegistrationRequest(
            address="",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        valid, error = req.validate(min_stake=32.0)
        assert not valid
        assert "address" in error.lower()
    
    def test_insuffient_stake(self):
        """Test request with insufficient stake."""
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=16.0,
        )
        
        valid, error = req.validate(min_stake=32.0)
        assert not valid
        assert "stake" in error.lower()
    
    def test_invalid_email(self):
        """Test request with invalid email."""
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="notanemail",
            stake_amount=32.0,
        )
        
        valid, error = req.validate(min_stake=32.0)
        assert not valid
        assert "email" in error.lower()


class TestValidatorRegistry:
    """Tests for ValidatorRegistry."""
    
    def test_registry_initialization(self):
        """Test registry initializes with correct default."""
        registry = ValidatorRegistry()
        assert registry.min_stake == 32.0
        assert len(registry.validators) == 0
    
    def test_custom_min_stake(self):
        """Test registry with custom min stake."""
        registry = ValidatorRegistry(min_stake=16.0)
        assert registry.min_stake == 16.0
    
    def test_register_validator(self):
        """Test registering a validator."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        validator = registry.register_validator(req)
        
        assert validator.validator_id is not None
        assert validator.address == "validator1.localhost:50051"
        assert validator.stake == 32.0
        assert validator.status == ValidatorStatus.PENDING
        assert len(registry.validators) == 1
    
    def test_register_duplicate_address(self):
        """Test registering validator with duplicate address fails."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        registry.register_validator(req)
        
        # Try to register again with same address
        with pytest.raises(ValueError):
            registry.register_validator(req)
    
    def test_confirm_stake(self):
        """Test confirming validator stake."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        validator = registry.register_validator(req)
        assert validator.status == ValidatorStatus.PENDING
        
        confirmed = registry.confirm_stake(validator.validator_id)
        assert confirmed.status == ValidatorStatus.ACTIVE
        assert confirmed.last_heartbeat is not None
    
    def test_get_validator(self):
        """Test getting validator by ID."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        registered = registry.register_validator(req)
        retrieved = registry.get_validator(registered.validator_id)
        
        assert retrieved is not None
        assert retrieved.validator_id == registered.validator_id
    
    def test_get_validator_by_address(self):
        """Test getting validator by address."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Node Operator 1",
            email="operator1@example.com",
            stake_amount=32.0,
        )
        
        registered = registry.register_validator(req)
        retrieved = registry.get_validator_by_address("validator1.localhost:50051")
        
        assert retrieved is not None
        assert retrieved.validator_id == registered.validator_id
    
    def test_get_active_validators(self):
        """Test getting active validators."""
        registry = ValidatorRegistry()
        
        # Register and activate first validator
        req1 = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v1 = registry.register_validator(req1)
        registry.confirm_stake(v1.validator_id)
        
        # Register second validator but don't activate
        req2 = RegistrationRequest(
            address="validator2.localhost:50052",
            name="Operator 2",
            email="op2@example.com",
            stake_amount=32.0,
        )
        registry.register_validator(req2)
        
        active = registry.get_active_validators()
        assert len(active) == 1
        assert active[0].validator_id == v1.validator_id
    
    def test_get_total_stake(self):
        """Test getting total stake."""
        registry = ValidatorRegistry()
        
        for i in range(3):
            req = RegistrationRequest(
                address=f"validator{i}.localhost:500{i}",
                name=f"Operator {i}",
                email=f"op{i}@example.com",
                stake_amount=32.0,
            )
            registry.register_validator(req)
        
        assert registry.get_total_stake() == 96.0
    
    def test_get_active_stake(self):
        """Test getting active stake."""
        registry = ValidatorRegistry()
        
        # Register 3 validators
        for i in range(3):
            req = RegistrationRequest(
                address=f"validator{i}.localhost:500{i}",
                name=f"Operator {i}",
                email=f"op{i}@example.com",
                stake_amount=32.0,
            )
            v = registry.register_validator(req)
            
            # Only activate first 2
            if i < 2:
                registry.confirm_stake(v.validator_id)
        
        assert registry.get_active_stake() == 64.0  # 2 * 32
    
    def test_update_heartbeat(self):
        """Test updating validator heartbeat."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        old_heartbeat = v.last_heartbeat
        
        # Sleep to ensure time difference
        time.sleep(0.01)
        
        # Update heartbeat
        registry.update_heartbeat(v.validator_id)
        updated = registry.get_validator(v.validator_id)
        
        # Heartbeat should be more recent
        assert updated.last_heartbeat >= old_heartbeat
    
    def test_increment_models_validated(self):
        """Test incrementing models validated counter."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        
        assert v.models_validated == 0
        
        registry.increment_models_validated(v.validator_id)
        updated = registry.get_validator(v.validator_id)
        assert updated.models_validated == 1
    
    def test_add_reward(self):
        """Test adding reward to validator."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        
        assert v.rewards_earned == 0.0
        
        registry.add_reward(v.validator_id, 5.0)
        updated = registry.get_validator(v.validator_id)
        assert updated.rewards_earned == 5.0
    
    def test_slash_validator(self):
        """Test slashing validator stake."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        assert v.stake == 32.0
        assert v.status == ValidatorStatus.ACTIVE
        
        slashed = registry.slash_validator(v.validator_id, 8.0, "misbehavior")
        
        assert slashed.stake == 24.0
        assert slashed.penalties_paid == 8.0
        assert slashed.slashes_received == 1
    
    def test_slash_puts_below_minimum(self):
        """Test slash that brings stake below minimum."""
        registry = ValidatorRegistry(min_stake=32.0)
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        slashed = registry.slash_validator(v.validator_id, 16.0)
        
        assert slashed.stake == 16.0
        assert slashed.status == ValidatorStatus.SLASHED
    
    def test_deactivate_validator(self):
        """Test deactivating validator."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        assert v.status == ValidatorStatus.ACTIVE
        
        deactivated = registry.deactivate_validator(v.validator_id)
        assert deactivated.status == ValidatorStatus.INACTIVE
    
    def test_reactivate_validator(self):
        """Test reactivating validator."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        registry.deactivate_validator(v.validator_id)
        reactivated = registry.reactivate_validator(v.validator_id)
        
        assert reactivated.status == ValidatorStatus.ACTIVE
    
    def test_list_validators(self):
        """Test listing validators."""
        registry = ValidatorRegistry()
        
        for i in range(5):
            req = RegistrationRequest(
                address=f"validator{i}.localhost:500{i}",
                name=f"Operator {i}",
                email=f"op{i}@example.com",
                stake_amount=32.0,
            )
            registry.register_validator(req)
        
        all_validators = registry.list_validators()
        assert len(all_validators) == 5
        
        limited = registry.list_validators(limit=3)
        assert len(limited) == 3
    
    def test_get_validator_count(self):
        """Test getting validator count."""
        registry = ValidatorRegistry()
        
        # Register 3 validators
        validators = []
        for i in range(3):
            req = RegistrationRequest(
                address=f"validator{i}.localhost:500{i}",
                name=f"Operator {i}",
                email=f"op{i}@example.com",
                stake_amount=32.0,
            )
            v = registry.register_validator(req)
            validators.append(v)
        
        # Activate 2
        registry.confirm_stake(validators[0].validator_id)
        registry.confirm_stake(validators[1].validator_id)
        
        assert registry.get_validator_count() == 3
        assert registry.get_validator_count(ValidatorStatus.ACTIVE) == 2
        assert registry.get_validator_count(ValidatorStatus.PENDING) == 1
    
    def test_export_state(self):
        """Test exporting registry state."""
        registry = ValidatorRegistry()
        req = RegistrationRequest(
            address="validator1.localhost:50051",
            name="Operator 1",
            email="op1@example.com",
            stake_amount=32.0,
        )
        v = registry.register_validator(req)
        registry.confirm_stake(v.validator_id)
        
        state = registry.export_state()
        
        assert state["min_stake"] == 32.0
        assert len(state["validators"]) == 1
