"""
Dashboard API routes — reads authoritative state from the blockchain.

Validator / node data is always sourced from chain.state (on-chain truth).
Model upload/validation is a local off-chain operation (pre-admission staging).

Endpoints:
- GET  /dashboard/validators            — all active nodes from chain state
- GET  /dashboard/validators/{id}       — single node from chain state
- GET  /dashboard/stats                 — aggregate chain statistics
- POST /dashboard/models/upload         — upload & locally validate a model file
- GET  /dashboard/models                — list locally registered models
- GET  /dashboard/models/{id}           — single model info
- GET  /dashboard/models/{id}/validations
- GET  /dashboard/health
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from core.api.node_service import NodeService
from core.registry import (
    ModelValidator,
    ModelSpec,
    Framework,
    ModelRegistry,
    ModelState,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(request: Request) -> NodeService:
    """Pull the shared NodeService from FastAPI app state."""
    return request.app.state.node_service


# ── Response models ───────────────────────────────────────────────────────────

class ChainValidatorResponse(BaseModel):
    """Validator as represented on-chain."""
    node_id:       str
    address:       str
    node_type:     str
    endpoint:      str
    is_active:     bool
    pom_verified:  bool
    model_name:    str
    weights_hash:  str
    dataset_id:    str
    stake:         float
    reputation:    float
    registered_at: int          # block height


class DashboardStatsResponse(BaseModel):
    total_nodes:       int
    active_nodes:      int
    dnn_validators:    int
    pos_validators:    int
    total_stake:       float
    active_dnn_stake:  float
    chain_height:      int
    pending_txs:       int


class ModelUploadResponse(BaseModel):
    model_id: str
    name:     str
    version:  str
    status:   str
    message:  str


class ModelInfoResponse(BaseModel):
    model_id:         str
    name:             str
    author:           str
    version:          str
    framework:        str
    state:            str
    created_at:       str
    description:      str
    validation_count: int
    avg_accuracy:     Optional[float] = None
    avg_latency_ms:   Optional[float] = None


# ── Off-chain model registry (local staging) ──────────────────────────────────

_model_registry:  Optional[ModelRegistry]  = None
_model_validator: Optional[ModelValidator] = None


def _get_model_registry() -> ModelRegistry:
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry("models.db")
        _model_registry.initialize()
    return _model_registry


def _get_model_validator() -> ModelValidator:
    global _model_validator
    if _model_validator is None:
        _model_validator = ModelValidator()
    return _model_validator


# ── Validator endpoints (chain-authoritative) ─────────────────────────────────

@router.get("/validators", response_model=List[ChainValidatorResponse])
async def list_validators(
    node_type: Optional[str] = None,
    request:   Request       = None,
) -> List[ChainValidatorResponse]:
    """
    List active nodes from chain state.

    Query params:
    - node_type: filter by 'dnn' or 'pos' (default: all active)
    """
    svc   = _svc(request)
    state = svc.chain.state

    if node_type == "dnn":
        nodes = state.dnn_validators()
    elif node_type == "pos":
        nodes = state.pos_validators()
    else:
        nodes = state.active_nodes()

    return [
        ChainValidatorResponse(
            node_id       = n.node_id,
            address       = n.address,
            node_type     = n.node_type,
            endpoint      = n.endpoint,
            is_active     = n.is_active,
            pom_verified  = n.pom_verified,
            model_name    = n.model_name,
            weights_hash  = n.weights_hash,
            dataset_id    = n.dataset_id,
            stake         = state.stake_of(n.address),
            reputation    = state.reputation_of(n.address),
            registered_at = n.registered_at,
        )
        for n in nodes
    ]


@router.get("/validators/{node_id}", response_model=ChainValidatorResponse)
async def get_validator(node_id: str, request: Request = None) -> ChainValidatorResponse:
    """Get a single node's on-chain information."""
    svc   = _svc(request)
    state = svc.chain.state

    node = state.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    return ChainValidatorResponse(
        node_id       = node.node_id,
        address       = node.address,
        node_type     = node.node_type,
        endpoint      = node.endpoint,
        is_active     = node.is_active,
        pom_verified  = node.pom_verified,
        model_name    = node.model_name,
        weights_hash  = node.weights_hash,
        dataset_id    = node.dataset_id,
        stake         = state.stake_of(node.address),
        reputation    = state.reputation_of(node.address),
        registered_at = node.registered_at,
    )


# ── Stats endpoint (chain-authoritative) ──────────────────────────────────────

@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(request: Request = None) -> DashboardStatsResponse:
    """Aggregate statistics read directly from chain state."""
    svc   = _svc(request)
    state = svc.chain.state
    chain = svc.chain

    all_nodes       = list(state.nodes.values())
    active_nodes    = state.active_nodes()
    dnn_validators  = state.dnn_validators()
    pos_validators  = state.pos_validators()

    total_stake      = sum(state.stake_of(n.address) for n in all_nodes)
    active_dnn_stake = sum(state.stake_of(n.address) for n in dnn_validators)

    return DashboardStatsResponse(
        total_nodes      = len(all_nodes),
        active_nodes     = len(active_nodes),
        dnn_validators   = len(dnn_validators),
        pos_validators   = len(pos_validators),
        total_stake      = total_stake,
        active_dnn_stake = active_dnn_stake,
        chain_height     = chain.height,
        pending_txs      = svc.mempool.size,
    )


# ── Model management (local off-chain staging) ────────────────────────────────

@router.post("/models/upload", response_model=ModelUploadResponse)
async def upload_model(
    file:           UploadFile = File(...),
    name:           str        = Form(...),
    version:        str        = Form(...),
    framework:      str        = Form(...),
    description:    str        = Form(""),
    input_shape:    str        = Form(...),
    output_shape:   str        = Form(...),
    min_accuracy:   float      = Form(0.0),
    max_latency_ms: float      = Form(1000.0),
    max_size_mb:    float      = Form(1000.0),
) -> ModelUploadResponse:
    """
    Upload a model file for local validation (off-chain staging).

    Models that pass validation can then be submitted via a NODE_REGISTER_DNN
    transaction to enter the PoM admission process.
    """
    import tempfile, os

    model_registry  = _get_model_registry()
    model_validator = _get_model_validator()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, file.filename)
            content   = await file.read()
            with open(file_path, "wb") as fh:
                fh.write(content)

            try:
                spec = ModelSpec(
                    name          = name,
                    version       = version,
                    framework     = Framework(framework.lower()),
                    input_shape   = tuple(map(int, input_shape.strip("[]()").split(","))),
                    output_shape  = tuple(map(int, output_shape.strip("[]()").split(","))),
                    max_latency_ms = max_latency_ms,
                    max_size_mb   = max_size_mb,
                    min_accuracy  = min_accuracy,
                    author        = "uploader",
                    description   = description,
                    model_path    = file_path,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid model spec: {e}")

            validation_result = model_validator.validate(spec)

            model_id = f"{name}_{version}_{datetime.now(timezone.utc).timestamp()}"
            model_registry.register_model(
                model_id       = model_id,
                name           = name,
                author         = "uploader",
                version        = version,
                framework      = framework,
                input_shape    = input_shape,
                output_shape   = output_shape,
                description    = description,
                min_accuracy   = min_accuracy,
                max_latency_ms = max_latency_ms,
                max_size_mb    = max_size_mb,
                model_path     = file_path,
            )

            if validation_result.passed:
                model_registry.update_model_state(model_id, ModelState.APPROVED)
                status  = "approved"
                message = "Model validated successfully — ready for on-chain submission"
            else:
                model_registry.update_model_state(model_id, ModelState.INVALID)
                status  = "invalid"
                message = f"Validation failed: {'; '.join(validation_result.errors)}"

            return ModelUploadResponse(
                model_id = model_id,
                name     = name,
                version  = version,
                status   = status,
                message  = message,
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@router.get("/models", response_model=List[ModelInfoResponse])
async def list_models(
    state: Optional[str] = None,
    limit: int           = 100,
) -> List[ModelInfoResponse]:
    """List locally registered models."""
    model_registry = _get_model_registry()
    try:
        if state:
            models = model_registry.get_models_by_state(ModelState(state))
        else:
            models = model_registry.list_models(limit=limit)

        responses = []
        for m in models:
            stats = model_registry.get_benchmark_stats(m["model_id"])
            responses.append(ModelInfoResponse(
                model_id         = m["model_id"],
                name             = m["name"],
                author           = m["author"],
                version          = m["version"],
                framework        = m["framework"],
                state            = m["state"],
                created_at       = m["created_at"],
                description      = m.get("description", ""),
                validation_count = len(model_registry.get_model_validations(m["model_id"])),
                avg_accuracy     = stats.get("avg_accuracy"),
                avg_latency_ms   = stats.get("avg_latency"),
            ))
        return responses

    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id}", response_model=ModelInfoResponse)
async def get_model(model_id: str) -> ModelInfoResponse:
    model_registry = _get_model_registry()
    model = model_registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    stats      = model_registry.get_benchmark_stats(model_id)
    validations = model_registry.get_model_validations(model_id)
    return ModelInfoResponse(
        model_id         = model["model_id"],
        name             = model["name"],
        author           = model["author"],
        version          = model["version"],
        framework        = model["framework"],
        state            = model["state"],
        created_at       = model["created_at"],
        description      = model.get("description", ""),
        validation_count = len(validations),
        avg_accuracy     = stats.get("avg_accuracy"),
        avg_latency_ms   = stats.get("avg_latency"),
    )


@router.get("/models/{model_id}/validations")
async def get_model_validations(model_id: str) -> List[dict]:
    model_registry = _get_model_registry()
    if not model_registry.get_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")

    return [
        {
            "validator_id":  v["validator_id"],
            "timestamp":     v["timestamp"],
            "passed":        v["passed"],
            "checks_passed": v["checks_passed"],
            "checks_total":  v["checks_total"],
            "errors":        v["errors"],
            "warnings":      v["warnings"],
        }
        for v in model_registry.get_model_validations(model_id)
    ]


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
