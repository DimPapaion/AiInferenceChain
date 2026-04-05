"""
Integration tests for /llm/* routes.

Uses MockProvider — no real LLM is required.
Each test gets a fresh NodeService + app instance wired with the orchestrator.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api import create_app
from core.api.node_service import create_node_service
from core.llm import InferenceOrchestrator
from core.llm.provider import MockProvider
from core.node.identity import make_test_identity

# ── Constants ─────────────────────────────────────────────────────────────────

ALICE = make_test_identity(1)

GENESIS_ALLOC = {ALICE.address: 500_000.0}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client_with_orchestrator():
    svc  = create_node_service(initial_allocations=GENESIS_ALLOC, f=1)
    orch = InferenceOrchestrator(provider=MockProvider())
    app  = create_app(
        svc,
        node_id    = ALICE.address,
        endpoint   = "http://localhost:8000",
        dev_mode   = True,
        orchestrator = orch,
    )
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def client_without_orchestrator():
    """App created with no orchestrator — /llm/* should return 503."""
    svc = create_node_service(initial_allocations=GENESIS_ALLOC, f=1)
    app = create_app(
        svc,
        node_id    = ALICE.address,
        endpoint   = "http://localhost:8000",
        dev_mode   = True,
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ═════════════════════════════════════════════════════════════════════════════
# /llm/route
# ═════════════════════════════════════════════════════════════════════════════

class TestLLMRoute:
    def test_returns_200_with_required_fields(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/route",
            json={"image_description": "a photo of a dog on a beach"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "model_hint"  in body
        assert "dataset_id"  in body
        assert "description" in body
        assert "confidence"  in body

    def test_model_hint_is_string(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/route",
            json={"image_description": "traffic sign"},
        )
        assert r.status_code == 200
        assert isinstance(r.json()["model_hint"], str)
        assert len(r.json()["model_hint"]) > 0

    def test_confidence_is_between_0_and_1(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/route",
            json={"image_description": "airplane in blue sky"},
        )
        assert r.status_code == 200
        conf = r.json()["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_optional_fields_accepted(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/route",
            json={
                "image_description":  "a car",
                "available_datasets": ["cifar10", "svhn"],
                "available_models":   ["resnet20", "densenet40"],
            },
        )
        assert r.status_code == 200

    def test_no_orchestrator_returns_503(self, client_without_orchestrator):
        r = client_without_orchestrator.post(
            "/llm/route",
            json={"image_description": "a red car"},
        )
        assert r.status_code == 503

    def test_missing_image_description_returns_422(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/route", json={})
        assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# /llm/analyse
# ═════════════════════════════════════════════════════════════════════════════

class TestLLMAnalyse:
    def test_returns_200_with_required_fields(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/analyse", json={})
        assert r.status_code == 200
        body = r.json()
        assert "anomalous_nodes"   in body
        assert "reason"            in body
        assert "recommend_pom"     in body

    def test_anomalous_nodes_is_list(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/analyse", json={})
        assert r.status_code == 200
        assert isinstance(r.json()["anomalous_nodes"], list)

    def test_recommend_pom_is_list(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/analyse", json={})
        assert r.status_code == 200
        assert isinstance(r.json()["recommend_pom"], list)

    def test_with_explicit_context(self, client_with_orchestrator):
        ctx = {
            "validators": [
                {"node_id": "aa" * 20, "accuracy": 0.3, "quorum_miss_rate": 0.8},
            ]
        }
        r = client_with_orchestrator.post("/llm/analyse", json={"context": ctx})
        assert r.status_code == 200

    def test_no_orchestrator_returns_503(self, client_without_orchestrator):
        r = client_without_orchestrator.post("/llm/analyse", json={})
        assert r.status_code == 503
        assert "detail" in r.json()

# ═════════════════════════════════════════════════════════════════════════════
# /llm/decompose
# ═════════════════════════════════════════════════════════════════════════════

class TestLLMDecompose:
    def test_returns_200_with_subtasks(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/decompose",
            json={"task_description": "Classify 5 images and summarise results"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "subtasks" in body
        assert isinstance(body["subtasks"], list)

    def test_strategy_is_valid(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/decompose",
            json={"task_description": "Run two separate image queries"},
        )
        assert r.status_code == 200
        strategy = r.json().get("strategy")
        assert strategy in ("parallel", "sequential", None)

    def test_no_orchestrator_returns_503(self, client_without_orchestrator):
        r = client_without_orchestrator.post(
            "/llm/decompose",
            json={"task_description": "Test task"},
        )
        assert r.status_code == 503

    def test_missing_task_description_returns_422(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/decompose", json={})
        assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# /llm/explain
# ═════════════════════════════════════════════════════════════════════════════

class TestLLMExplain:
    def test_returns_200_with_answer(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/explain",
            json={"question": "How many blocks are in the chain?"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "answer" in body
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_with_explicit_context(self, client_with_orchestrator):
        r = client_with_orchestrator.post(
            "/llm/explain",
            json={
                "question": "Who has the highest stake?",
                "context":  {"blocks": 3, "nodes": 2},
            },
        )
        assert r.status_code == 200

    def test_no_orchestrator_returns_503(self, client_without_orchestrator):
        r = client_without_orchestrator.post(
            "/llm/explain",
            json={"question": "What is the current block height?"},
        )
        assert r.status_code == 503

    def test_missing_question_returns_422(self, client_with_orchestrator):
        r = client_with_orchestrator.post("/llm/explain", json={})
        assert r.status_code == 422
