"""Tests for dashboard API routes — now backed by chain state."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routes import dashboard as dashboard_module
from core.api.routes.dashboard import router
from core.api.node_service import create_node_service
from core.registry import ModelRegistry, ModelState


# ── Fixtures ──────────────────────────────────────────────────────────────────

DNN_NODE = {
    "address":     "0xDNN1",
    "public_key":  "pk_dnn1",
    "model_name":  "resnet18",
    "weights_hash": "abc123",
    "dataset_id":  "cifar10",
    "endpoint":    "http://127.0.0.1:8010",
    "stake":       50_000.0,
}


@pytest.fixture
def node_service():
    """In-memory NodeService with one pre-admitted DNN node."""
    return create_node_service(
        initial_allocations={"0xDNN1": 100_000.0},
        initial_dnn_nodes=[DNN_NODE],
    )


@pytest.fixture
def app(node_service):
    """FastAPI app with node_service in state."""
    _app = FastAPI()
    _app.include_router(router)
    _app.state.node_service = node_service
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_model_registry():
    """Reset module-level model registry between tests."""
    dashboard_module._model_registry  = None
    dashboard_module._model_validator = None
    yield
    dashboard_module._model_registry  = None
    dashboard_module._model_validator = None


@pytest.fixture
def temp_model_registry():
    """Inject a temp-dir backed ModelRegistry into the dashboard module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path  = str(Path(tmpdir) / "test.db")
        registry = ModelRegistry(db_path)
        registry.initialize()
        dashboard_module._model_registry = registry
        yield registry
        registry.close()
        dashboard_module._model_registry = None


# ── Validator endpoints (chain-backed) ────────────────────────────────────────

class TestValidatorEndpoints:
    def test_list_all_validators(self, client):
        """GET /dashboard/validators returns on-chain nodes."""
        resp = client.get("/dashboard/validators")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        node = data[0]
        assert node["node_type"]  == "dnn"
        assert node["is_active"]  is True
        assert node["stake"]      == 50_000.0
        assert node["model_name"] == "resnet18"

    def test_list_dnn_validators(self, client):
        """Filtering by node_type=dnn returns only DNN nodes."""
        resp = client.get("/dashboard/validators", params={"node_type": "dnn"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(n["node_type"] == "dnn" for n in data)

    def test_get_validator_by_id(self, client, node_service):
        """GET /dashboard/validators/{id} returns a single node."""
        node_id = list(node_service.chain.state.nodes.keys())[0]
        resp    = client.get(f"/dashboard/validators/{node_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"]    == node_id
        assert data["model_name"] == "resnet18"
        assert data["stake"]      == 50_000.0

    def test_get_nonexistent_validator(self, client):
        resp = client.get("/dashboard/validators/nonexistent_node_id")
        assert resp.status_code == 404


# ── Stats endpoint (chain-backed) ─────────────────────────────────────────────

class TestStatsEndpoint:
    def test_dashboard_stats(self, client):
        """GET /dashboard/stats returns chain-accurate counts."""
        resp = client.get("/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dnn_validators"]  >= 1
        assert data["active_nodes"]    >= 1
        assert data["active_dnn_stake"] == 50_000.0
        assert data["chain_height"]    == 0   # genesis only
        assert "pending_txs" in data

    def test_health_check(self, client):
        resp = client.get("/dashboard/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ── Model endpoints (local off-chain registry) ────────────────────────────────

class TestModelEndpoints:
    def test_list_models_empty(self, client, temp_model_registry):
        resp = client.get("/dashboard/models")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_model_not_found(self, client, temp_model_registry):
        resp = client.get("/dashboard/models/nonexistent")
        assert resp.status_code == 404

    def test_get_model_validations_not_found(self, client, temp_model_registry):
        resp = client.get("/dashboard/models/nonexistent/validations")
        assert resp.status_code == 404

    def test_get_model_with_validations(self, client, temp_model_registry):
        """Register a model and attach a validation record."""
        registry = temp_model_registry
        model_id = registry.register_model(
            model_id="m1",
            name="MyModel",
            author="tester",
            version="1.0",
            framework="pytorch",
            input_shape="[3,32,32]",
            output_shape="[10]",
            model_path="/tmp/fake.pth",
        )
        registry.add_validation(
            model_id=model_id,
            validator_id="node_a",
            passed=True,
            checks_passed=5,
            checks_total=5,
            errors=[],
        )

        resp = client.get(f"/dashboard/models/{model_id}/validations")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["passed"]  # SQLite returns 1 for True

    def test_list_models_by_state(self, client, temp_model_registry):
        """Filtering by state returns matching models only."""
        registry = temp_model_registry
        mid = registry.register_model(
            model_id="m2",
            name="AModel",
            author="tester",
            version="2.0",
            framework="onnx",
            input_shape="[1,3,224,224]",
            output_shape="[1000]",
            model_path="/tmp/fake2.onnx",
        )
        registry.update_model_state(mid, ModelState.APPROVED)

        resp = client.get("/dashboard/models", params={"state": "approved"})
        assert resp.status_code == 200
        data = resp.json()
        assert any(m["model_id"] == mid for m in data)

    def test_list_models_invalid_state(self, client, temp_model_registry):
        resp = client.get("/dashboard/models", params={"state": "invalid_state"})
        assert resp.status_code == 400
