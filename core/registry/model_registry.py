"""
Model registry database schema and management for InferenceChain.

Tracks:
- Registered models with metadata
- Validation history
- Benchmark results
- Model versions
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

from core.utils.logger import get_logger


class ModelState(str, Enum):
    """Model registration state."""
    DRAFT = "draft"          # Not yet validated
    VALIDATING = "validating"  # Currently being validated
    APPROVED = "approved"    # Passed validation, can be used
    REJECTED = "rejected"    # Failed validation, cannot be used
    DEPRECATED = "deprecated"  # Old version, replaced
    ARCHIVED = "archived"    # Permanently removed


@dataclass
class ModelBenchmark:
    """Benchmark results for a model."""
    
    model_id: str
    validator_id: str
    timestamp: datetime
    inference_time_ms: float
    accuracy: float
    cost: float  # Computational cost units
    notes: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "validator_id": self.validator_id,
            "timestamp": self.timestamp.isoformat(),
            "inference_time_ms": self.inference_time_ms,
            "accuracy": self.accuracy,
            "cost": self.cost,
            "notes": self.notes,
        }


@dataclass
class ModelValidationRecord:
    """Record of model validation."""
    
    model_id: str
    validator_id: str
    timestamp: datetime
    passed: bool
    checks_passed: int
    checks_total: int
    errors: List[str]
    warnings: List[str]
    tx_hash: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "validator_id": self.validator_id,
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed,
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "errors": self.errors,
            "warnings": self.warnings,
            "tx_hash": self.tx_hash,
        }


class ModelRegistry:
    """
    Manages model registry database for InferenceChain.
    
    Database schema:
    - models: Core model metadata
    - model_versions: Version history
    - validations: Validation history
    - benchmarks: Performance benchmarks
    
    Usage:
        registry = ModelRegistry("models.db")
        registry.initialize()
        
        # Register model
        model_id = registry.register_model(
            name="resnet50",
            author="validator1",
            framework="pytorch",
            input_shape="[3,224,224]",
            output_shape="[1000]",
            version="1.0.0",
        )
        
        # Record validation
        registry.add_validation(
            model_id=model_id,
            validator_id="val1",
            passed=True,
            checks_passed=5,
            checks_total=5,
            errors=[],
            warnings=[],
        )
        
        # Record benchmark
        registry.add_benchmark(
            model_id=model_id,
            validator_id="val1",
            inference_time_ms=45.2,
            accuracy=0.92,
        )
        
        # Query
        model = registry.get_model(model_id)
        validations = registry.get_model_validations(model_id)
    """
    
    def __init__(self, db_path: str = "models.db"):
        """
        Initialize model registry.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self.logger = get_logger("model_registry")
        self.connection = None
    
    def initialize(self) -> None:
        """Initialize database schema."""
        self.connection = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,  # Allow multi-threaded access
        )
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        
        # Models table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                author TEXT NOT NULL,
                version TEXT NOT NULL,
                framework TEXT NOT NULL,
                input_shape TEXT NOT NULL,
                output_shape TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'draft',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                description TEXT,
                min_accuracy REAL,
                max_latency_ms REAL,
                max_size_mb REAL,
                model_path TEXT,
                metadata TEXT,
                UNIQUE(name, version)
            )
        """)
        
        # Model versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                version TEXT NOT NULL,
                model_path TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                created_by TEXT,
                notes TEXT,
                FOREIGN KEY (model_id) REFERENCES models(model_id)
            )
        """)
        
        # Validations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validations (
                validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                validator_id TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                passed BOOLEAN NOT NULL,
                checks_passed INTEGER NOT NULL,
                checks_total INTEGER NOT NULL,
                errors TEXT,
                warnings TEXT,
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(model_id)
            )
        """)
        
        # Benchmarks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                benchmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                validator_id TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                inference_time_ms REAL NOT NULL,
                accuracy REAL NOT NULL,
                cost REAL NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(model_id)
            )
        """)
        
        # Create indices for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_models_author ON models(author)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_models_state ON models(state)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_validations_model ON validations(model_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_benchmarks_model ON benchmarks(model_id)
        """)
        
        self.connection.commit()
        self.logger.info("Model registry database initialized")
    
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
    
    def register_model(
        self,
        model_id: str,
        name: str,
        author: str,
        version: str,
        framework: str,
        input_shape: str,  # JSON string
        output_shape: str,  # JSON string
        description: str = "",
        min_accuracy: float = 0.0,
        max_latency_ms: float = 1000.0,
        max_size_mb: float = 1000.0,
        model_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register a new model.
        
        Args:
            model_id: Unique model ID
            name: Model name
            author: Author/creator
            version: Version string
            framework: Framework (pytorch, tensorflow, onnx)
            input_shape: JSON string of input shape
            output_shape: JSON string of output shape
            description: Model description
            min_accuracy: Minimum acceptable accuracy
            max_latency_ms: Maximum acceptable latency
            max_size_mb: Maximum model size
            model_path: Path to model file
            metadata: Additional metadata
            
        Returns:
            model_id
        """
        cursor = self.connection.cursor()
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO models (
                model_id, name, author, version, framework,
                input_shape, output_shape, state,
                created_at, updated_at, description,
                min_accuracy, max_latency_ms, max_size_mb,
                model_path, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_id, name, author, version, framework,
            input_shape, output_shape, ModelState.DRAFT.value,
            now, now, description,
            min_accuracy, max_latency_ms, max_size_mb,
            model_path,
            json.dumps(metadata or {}),
        ))
        
        # Create initial version
        cursor.execute("""
            INSERT INTO model_versions (
                model_id, version, model_path, state, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            model_id, version, model_path, ModelState.DRAFT.value, now, author
        ))
        
        self.connection.commit()
        
        self.logger.info(
            "Model registered",
            context={
                "model_id": model_id,
                "name": name,
                "version": version,
            },
        )
        
        return model_id
    
    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model by ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM models WHERE model_id = ?", (model_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_model_by_name_version(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        """Get model by name and version."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM models WHERE name = ? AND version = ?",
            (name, version),
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_models_by_author(self, author: str) -> List[Dict[str, Any]]:
        """Get all models by author."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM models WHERE author = ? ORDER BY created_at DESC",
            (author,),
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_models_by_state(self, state: ModelState) -> List[Dict[str, Any]]:
        """Get models by state."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM models WHERE state = ? ORDER BY created_at DESC",
            (state.value,),
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_approved_models(self) -> List[Dict[str, Any]]:
        """Get approved models."""
        return self.get_models_by_state(ModelState.APPROVED)
    
    def update_model_state(self, model_id: str, new_state: ModelState) -> None:
        """Update model state."""
        cursor = self.connection.cursor()
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            UPDATE models SET state = ?, updated_at = ? WHERE model_id = ?
        """, (new_state.value, now, model_id))
        
        self.connection.commit()
        
        self.logger.info(
            "Model state updated",
            context={
                "model_id": model_id,
                "state": new_state.value,
            },
        )
    
    def add_validation(
        self,
        model_id: str,
        validator_id: str,
        passed: bool,
        checks_passed: int,
        checks_total: int,
        errors: List[str] = None,
        warnings: List[str] = None,
        tx_hash: str = None,
    ) -> int:
        """
        Record model validation.
        
        Returns:
            validation_id
        """
        cursor = self.connection.cursor()
        timestamp = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO validations (
                model_id, validator_id, timestamp,
                passed, checks_passed, checks_total,
                errors, warnings, tx_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_id, validator_id, timestamp,
            passed, checks_passed, checks_total,
            json.dumps(errors or []),
            json.dumps(warnings or []),
            tx_hash,
        ))
        
        self.connection.commit()
        
        # If validation passed, update model state to approved
        if passed:
            self.update_model_state(model_id, ModelState.APPROVED)
        
        return cursor.lastrowid
    
    def get_model_validations(self, model_id: str) -> List[Dict[str, Any]]:
        """Get validation history for model."""
        cursor = self.connection.cursor()
        cursor.execute(
            """SELECT * FROM validations
               WHERE model_id = ?
               ORDER BY timestamp DESC""",
            (model_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def add_benchmark(
        self,
        model_id: str,
        validator_id: str,
        inference_time_ms: float,
        accuracy: float,
        cost: float = 1.0,
        notes: str = "",
    ) -> int:
        """
        Record benchmark result.
        
        Returns:
            benchmark_id
        """
        cursor = self.connection.cursor()
        timestamp = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO benchmarks (
                model_id, validator_id, timestamp,
                inference_time_ms, accuracy, cost, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            model_id, validator_id, timestamp,
            inference_time_ms, accuracy, cost, notes,
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def get_model_benchmarks(self, model_id: str) -> List[Dict[str, Any]]:
        """Get benchmark history for model."""
        cursor = self.connection.cursor()
        cursor.execute(
            """SELECT * FROM benchmarks
               WHERE model_id = ?
               ORDER BY timestamp DESC""",
            (model_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_benchmark_stats(self, model_id: str) -> Dict[str, float]:
        """Get aggregate benchmark statistics."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                AVG(inference_time_ms) as avg_latency,
                MIN(inference_time_ms) as min_latency,
                MAX(inference_time_ms) as max_latency,
                AVG(accuracy) as avg_accuracy,
                COUNT(*) as total_benchmarks
            FROM benchmarks
            WHERE model_id = ?
        """, (model_id,))
        
        row = cursor.fetchone()
        if row:
            d = dict(row)
            return {k: v for k, v in d.items()}
        
        return {
            "avg_latency": 0,
            "min_latency": 0,
            "max_latency": 0,
            "avg_accuracy": 0,
            "total_benchmarks": 0,
        }
    
    def list_models(
        self,
        limit: int = 100,
        state: ModelState = None,
    ) -> List[Dict[str, Any]]:
        """List models."""
        cursor = self.connection.cursor()
        
        if state:
            cursor.execute(
                "SELECT * FROM models WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                (state.value, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM models ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_total_models(self) -> int:
        """Get total model count."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM models")
        return cursor.fetchone()[0]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        cursor = self.connection.cursor()
        
        # Count by state
        cursor.execute("""
            SELECT state, COUNT(*) as count
            FROM models
            GROUP BY state
        """)
        state_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Count by framework
        cursor.execute("""
            SELECT framework, COUNT(*) as count
            FROM models
            GROUP BY framework
        """)
        framework_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "total_models": self.get_total_models(),
            "by_state": state_counts,
            "by_framework": framework_counts,
            "approved": state_counts.get(ModelState.APPROVED.value, 0),
            "pending": state_counts.get(ModelState.VALIDATING.value, 0),
        }
