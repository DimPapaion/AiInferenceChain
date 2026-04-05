"""
LLM Orchestration routes.

POST /llm/route         — recommend model_hint + dataset_id for an image description
POST /llm/analyse       — scan validators for anomalies, recommend PoM re-challenges
POST /llm/decompose     — break a complex task into parallel inference sub-tasks
POST /llm/explain       — natural-language Q&A about the current chain state

These endpoints require an LLM provider to be configured. If none is configured
the server returns 503 with instructions.  All endpoints degrade safely.

Provider setup (in node_runner.py / create_app):
    from core.llm import InferenceOrchestrator, OllamaProvider
    orchestrator = InferenceOrchestrator(provider=OllamaProvider())
    app.state.orchestrator = orchestrator
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.api.deps import get_service
from core.api.node_service import NodeService

router = APIRouter(prefix="/llm", tags=["llm"])


# ── Request / Response schemas ────────────────────────────────────────────────

class RouteRequest(BaseModel):
    image_description:   str
    available_datasets:  list[str] | None = None
    available_models:    list[str] | None = None


class RouteResponse(BaseModel):
    model_hint:  str
    dataset_id:  str
    description: str
    confidence:  float


class AnalyseRequest(BaseModel):
    """
    Optionally pass extra context. If omitted, the endpoint builds a summary
    from the live chain state automatically.
    """
    context: dict | None = None


class AnalyseResponse(BaseModel):
    anomalous_nodes: list[str]
    reason:          str
    recommend_pom:   list[str]


class DecomposeRequest(BaseModel):
    task_description: str


class DecomposeSubTask(BaseModel):
    description: str
    model_hint:  str
    dataset_id:  str
    image_hash:  str


class DecomposeResponse(BaseModel):
    subtasks:  list[DecomposeSubTask]
    strategy:  str
    reasoning: str


class ExplainRequest(BaseModel):
    question: str
    context:  dict | None = None


class ExplainResponse(BaseModel):
    answer: str


# ── Dependency: resolve orchestrator from app state ───────────────────────────

def _get_orchestrator(request: Request):
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(
            status_code = 503,
            detail = (
                "LLM orchestrator not configured. "
                "Set app.state.orchestrator = InferenceOrchestrator(provider=...) "
                "in your node startup. See core/llm/README for instructions."
            ),
        )
    return orch


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/route", response_model=RouteResponse)
async def route_request(
    body:    RouteRequest,
    request: Request,
    svc:     NodeService = Depends(get_service),
):
    """
    Recommend which model and dataset this inference request should target.

    The LLM analyses the image description and network's available validators
    to produce an intelligent routing hint. Attach model_hint + dataset_id
    to your InferenceRequest transaction payload.
    """
    orch = _get_orchestrator(request)

    # Pass available datasets/models from chain state if not provided explicitly
    if body.available_datasets is None:
        from core.blockchain.constants import SUPPORTED_DATASETS
        avail_ds = list(SUPPORTED_DATASETS)
    else:
        avail_ds = body.available_datasets

    if body.available_models is None:
        dnn_nodes   = svc.chain.state.dnn_validators()
        avail_models = list({n.model_name for n in dnn_nodes if n.model_name})
    else:
        avail_models = body.available_models

    decision = await orch.route_request(
        image_description   = body.image_description,
        available_datasets  = avail_ds,
        available_models    = avail_models,
    )
    return RouteResponse(
        model_hint  = decision.model_hint,
        dataset_id  = decision.dataset_id,
        description = decision.description,
        confidence  = decision.confidence,
    )


@router.post("/analyse", response_model=AnalyseResponse)
async def analyse_validators(
    body:    AnalyseRequest,
    request: Request,
    svc:     NodeService = Depends(get_service),
):
    """
    Scan validator behaviour for anomalies and return a list of node_ids
    that are behaving suspiciously. Optionally recommends re-PoM challenges.

    The endpoint automatically builds a chain state summary unless you
    supply one in body.context.
    """
    orch = _get_orchestrator(request)

    if body.context:
        summary = body.context
    else:
        summary = _build_validator_summary(svc)

    report = await orch.analyse_validators(summary)
    return AnalyseResponse(
        anomalous_nodes = report.anomalous_nodes,
        reason          = report.reason,
        recommend_pom   = report.recommend_pom,
    )


@router.post("/decompose", response_model=DecomposeResponse)
async def decompose_task(
    body:    DecomposeRequest,
    request: Request,
):
    """
    Break a complex multi-image or multi-question task into individual
    InferenceRequest sub-tasks that can be submitted in parallel.

    Returns a list of sub-tasks with model_hint / dataset_id already filled.
    The caller is responsible for setting image_hash on each sub-task before
    submitting to /inference/request.
    """
    orch = _get_orchestrator(request)
    result = await orch.decompose_task(body.task_description)
    return DecomposeResponse(
        subtasks  = [
            DecomposeSubTask(
                description = st.description,
                model_hint  = st.model_hint,
                dataset_id  = st.dataset_id,
                image_hash  = st.image_hash,
            )
            for st in result.subtasks
        ],
        strategy  = result.strategy,
        reasoning = result.reasoning,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain_chain_state(
    body:    ExplainRequest,
    request: Request,
    svc:     NodeService = Depends(get_service),
):
    """
    Ask a natural-language question about the current chain state.

    Examples:
      - "Which validator has the highest reputation?"
      - "Why was the last block a QoI block instead of PoS?"
      - "How many tokens does address 0xabc... hold?"
    """
    orch = _get_orchestrator(request)

    if body.context:
        summary = body.context
    else:
        summary = _build_chain_summary(svc)

    answer = await orch.explain_chain_state(body.question, summary)
    return ExplainResponse(answer=answer)


# ── Private: chain state summarisers ─────────────────────────────────────────

def _build_validator_summary(svc: NodeService) -> dict:
    """Build a compact validator summary for the LLM to analyse."""
    state    = svc.chain.state
    dnn      = state.dnn_validators()

    validators = []
    for n in dnn:
        validators.append({
            "node_id":     n.node_id[:16] + "…",
            "model":       n.model_name,
            "dataset":     n.dataset_id,
            "reputation":  round(state.reputations.get(n.node_id, 0.0), 4),
            "stake":       round(state.stake_of(n.node_id), 2),
            "is_active":   n.is_active,
            "pom_block":   n.pom_block,
        })

    return {
        "height":        svc.chain.height,
        "num_dnn_nodes": len(dnn),
        "validators":    validators,
    }


def _build_chain_summary(svc: NodeService) -> dict:
    """Build a compact chain summary for Q&A."""
    state  = svc.chain.state
    tip    = svc.chain.tip

    return {
        "height":          svc.chain.height,
        "tip_hash":        tip.hash[:16] + "…",
        "tip_type":        tip.header.block_type.value,
        "total_nodes":     len(state.nodes),
        "active_dnn":      sum(1 for n in state.dnn_validators() if n.is_active),
        "mempool_pending": svc.mempool.size,
        "top_reputations": sorted(
            [
                {"node_id": nid[:12] + "…", "rep": round(rep, 4)}
                for nid, rep in state.reputations.items()
            ],
            key=lambda x: x["rep"], reverse=True
        )[:5],
    }
