"""
InferenceOrchestrator — LLM-powered coordination layer for InferenceChain.

This is the "brain" that sits above the deterministic blockchain layer.
It uses an LLM to make intelligent decisions about inference requests
without ever touching consensus, key management, or quorum selection.

Capabilities
------------
1. route_request(image_description)
   → Recommends model_hint and dataset_id to attach to an InferenceRequest tx.
   → Enables smart dispatch: "this looks like a street scene → SVHN-trained nodes"

2. analyse_validators(chain_state_summary)
   → Scans reputation history for anomalous validator behaviour.
   → Returns a list of node_ids to flag for PoM re-challenge.

3. decompose_task(complex_description)
   → Breaks a multi-question or multi-image task into parallel sub-requests.
   → Returns a list of InferenceSubTask objects that the caller submits individually.

4. explain_chain_state(question, chain_state_summary)
   → Natural language Q&A: "why did block 42 fail?" "which validator is most trusted?"

All methods return typed Python objects and never raise on LLM error —
they degrade gracefully to safe defaults so the chain keeps running.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.llm.provider import LLMProvider, LLMMessage, MockProvider

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RoutingDecision:
    """
    Recommended routing for an inference request.
    These values should be attached as model_hint / dataset_id on the tx payload.
    """
    model_hint:  str   = "any"       # specific model name, or "any"
    dataset_id:  str   = "cifar10"   # dataset the node must be trained on
    description: str   = ""          # human-readable explanation
    confidence:  float = 0.0         # 0.0–1.0


@dataclass
class AnomalyReport:
    """
    Result of the validator anomaly scan.
    anomalous_nodes : node_ids flagged as suspicious
    recommend_pom   : node_ids that should be re-challenged via PoM
    """
    anomalous_nodes: list[str] = field(default_factory=list)
    reason:          str       = ""
    recommend_pom:   list[str] = field(default_factory=list)


@dataclass
class InferenceSubTask:
    """One sub-request in a decomposed multi-part inference job."""
    description: str
    model_hint:  str = "any"
    dataset_id:  str = "cifar10"
    image_hash:  str = ""          # filled in by caller when submitting the tx


@dataclass
class DecomposedTask:
    """
    Result of decomposing a complex task into parallel sub-tasks.
    strategy: "sequential" | "parallel"
    """
    subtasks:  list[InferenceSubTask] = field(default_factory=list)
    strategy:  str                    = "sequential"
    reasoning: str                    = ""


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class InferenceOrchestrator:
    """
    LLM-powered orchestration layer.

    Usage
    -----
        from core.llm import InferenceOrchestrator, OllamaProvider

        orchestrator = InferenceOrchestrator(provider=OllamaProvider())

        # Recommend routing for a new image
        decision = await orchestrator.route_request(
            image_description="Street scene with visible house numbers"
        )
        # decision.model_hint == "any"  or  "VGG16"  etc.
        # decision.dataset_id == "svhn"

        # Check validators for anomalies
        report = await orchestrator.analyse_validators(chain_summary)
    """

    # ── System prompts ────────────────────────────────────────────────────────
    _ROUTING_SYSTEM = """You are an intelligent routing agent for InferenceChain,
a decentralised DNN inference blockchain. Your job is to recommend which DNN model
and dataset a submitted inference request should be routed to.

Available datasets: cifar10, svhn, stl10, fmnist, blaze
Available model hints: any, resnet20, resnet32, vgg11, vgg16, mobilenet_v2, densenet, wide_resnet

Rules:
- "cifar10" is for general natural images (10 classes: airplane, car, bird, cat, deer, dog, frog, horse, ship, truck)
- "svhn" is for digit/number recognition in natural scenes (street view numbers)
- "stl10" is for high-resolution natural scene images
- "fmnist" is for fashion/clothing item classification
- "blaze" is for wildfire/disaster images (fire, burnt, non-burnt)

Respond ONLY with a JSON object matching exactly this schema (no markdown, no explanation outside JSON):
{
  "model_hint":  "<model name or 'any'>",
  "dataset_id":  "<one of the available datasets>",
  "description": "<one sentence explaining your choice>",
  "confidence":  <float 0.0-1.0>
}"""

    _ANOMALY_SYSTEM = """You are a validator health monitor for InferenceChain.
You will receive a summary of recent validator behaviour including reputation scores,
consensus participation rates, accuracy on QoI rounds, and any slash events.

Your job is to identify validators that show suspicious patterns:
- Consistently low QoI accuracy (below 0.6)
- Sudden large drops in reputation
- Participating in consensus but frequently disagreeing with 2f+1 majority
- Not participating when elected to quorum

Respond ONLY with a JSON object matching exactly this schema (no markdown):
{
  "anomalous_nodes": ["<node_id>", ...],
  "reason":          "<explanation>",
  "recommend_pom":   ["<node_id>", ...]
}
If nothing is anomalous, return empty lists."""

    _DECOMPOSE_SYSTEM = """You are a task decomposition agent for InferenceChain.
Users sometimes submit complex requests that involve multiple images or multiple
classification questions. Your job is to break these into individual sub-tasks,
each of which maps to a single InferenceRequest transaction.

Respond ONLY with a JSON object matching exactly this schema (no markdown):
{
  "subtasks": [
    {"description": "<what this sub-task classifies>", "model_hint": "<model or 'any'>", "dataset_id": "<dataset>"},
    ...
  ],
  "strategy": "sequential" | "parallel",
  "reasoning": "<one sentence>"
}"""

    _EXPLAIN_SYSTEM = """You are a blockchain analyst for InferenceChain, a decentralised
DNN inference platform. Answer questions about the chain state concisely and accurately.
If information is insufficient, say so clearly. Do not speculate beyond the data given."""

    def __init__(
        self,
        provider:    LLMProvider | None  = None,
        temperature: float               = 0.0,
        max_tokens:  int                 = 512,
    ) -> None:
        self._provider    = provider or MockProvider()
        self._temperature = temperature
        self._max_tokens  = max_tokens

    # ── 1. Request routing ────────────────────────────────────────────────────

    async def route_request(
        self,
        image_description: str,
        available_datasets: list[str] | None = None,
        available_models:   list[str] | None = None,
    ) -> RoutingDecision:
        """
        Given a natural-language description of an image (e.g. from filename,
        user label, or EXIF metadata), recommend model_hint and dataset_id.

        Returns a safe default (model_hint="any", dataset_id="cifar10") on error.
        """
        user_content = f"Image description: {image_description}"
        if available_datasets:
            user_content += f"\nAvailable datasets on this network: {', '.join(available_datasets)}"
        if available_models:
            user_content += f"\nAvailable model architectures: {', '.join(available_models)}"

        try:
            reply = await self._provider.complete(
                messages    = [
                    LLMMessage(role="system",  content=self._ROUTING_SYSTEM),
                    LLMMessage(role="user",    content=user_content),
                ],
                temperature = self._temperature,
                max_tokens  = self._max_tokens,
            )
            data = _parse_json(reply)
            return RoutingDecision(
                model_hint  = str(data.get("model_hint", "any")),
                dataset_id  = str(data.get("dataset_id", "cifar10")),
                description = str(data.get("description", "")),
                confidence  = float(data.get("confidence", 0.0)),
            )
        except Exception as exc:
            log.warning("route_request LLM call failed: %s — using safe default", exc)
            return RoutingDecision()

    # ── 2. Validator anomaly detection ────────────────────────────────────────

    async def analyse_validators(
        self,
        chain_state_summary: dict,
    ) -> AnomalyReport:
        """
        Analyse recent validator behaviour and flag suspicious nodes.

        chain_state_summary should contain:
          - validators: list of {node_id, reputation, qoi_accuracy, slash_count, ...}
          - recent_rounds: list of recent QoI round outcomes
          - height: current chain height

        Returns an AnomalyReport. On error returns an empty (safe) report.
        """
        user_content = (
            "Chain state summary (JSON):\n"
            + json.dumps(chain_state_summary, indent=2)[:3000]   # cap size
        )
        try:
            reply = await self._provider.complete(
                messages    = [
                    LLMMessage(role="system", content=self._ANOMALY_SYSTEM),
                    LLMMessage(role="user",   content=user_content),
                ],
                temperature = self._temperature,
                max_tokens  = self._max_tokens,
            )
            data = _parse_json(reply)
            return AnomalyReport(
                anomalous_nodes = list(data.get("anomalous_nodes", [])),
                reason          = str(data.get("reason", "")),
                recommend_pom   = list(data.get("recommend_pom", [])),
            )
        except Exception as exc:
            log.warning("analyse_validators LLM call failed: %s", exc)
            return AnomalyReport()

    # ── 3. Task decomposition ─────────────────────────────────────────────────

    async def decompose_task(
        self,
        task_description: str,
    ) -> DecomposedTask:
        """
        Break a complex multi-image or multi-question task into parallel sub-tasks.

        Example:
            decompose_task("Classify these 10 street images and also identify any
                            vehicles in the CIFAR-10 test batch")
            → 2 subtasks: one routed to svhn, one to cifar10

        Returns a single-subtask DecomposedTask on error (safe default).
        """
        try:
            reply = await self._provider.complete(
                messages    = [
                    LLMMessage(role="system", content=self._DECOMPOSE_SYSTEM),
                    LLMMessage(role="user",   content=f"Task: {task_description}"),
                ],
                temperature = self._temperature,
                max_tokens  = self._max_tokens,
            )
            data = _parse_json(reply)
            subtasks = [
                InferenceSubTask(
                    description = str(st.get("description", "")),
                    model_hint  = str(st.get("model_hint", "any")),
                    dataset_id  = str(st.get("dataset_id", "cifar10")),
                )
                for st in data.get("subtasks", [])
            ]
            return DecomposedTask(
                subtasks  = subtasks or [InferenceSubTask(description=task_description)],
                strategy  = str(data.get("strategy", "sequential")),
                reasoning = str(data.get("reasoning", "")),
            )
        except Exception as exc:
            log.warning("decompose_task LLM call failed: %s", exc)
            return DecomposedTask(
                subtasks=[InferenceSubTask(description=task_description)]
            )

    # ── 4. Chain state Q&A ────────────────────────────────────────────────────

    async def explain_chain_state(
        self,
        question:            str,
        chain_state_summary: dict,
    ) -> str:
        """
        Answer a natural language question about the chain state.

        Returns the answer as a plain string. On error returns a fallback message.
        """
        context = json.dumps(chain_state_summary, indent=2)[:4000]
        try:
            reply = await self._provider.complete(
                messages    = [
                    LLMMessage(role="system",    content=self._EXPLAIN_SYSTEM),
                    LLMMessage(role="user",      content=f"Chain state:\n{context}"),
                    LLMMessage(role="user",      content=f"Question: {question}"),
                ],
                temperature = 0.2,    # slightly higher for explanation tasks
                max_tokens  = 800,
            )
            return reply
        except Exception as exc:
            log.warning("explain_chain_state LLM call failed: %s", exc)
            return f"Unable to answer: LLM provider error ({exc})"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """
    Parse a JSON string from the LLM reply.
    Strips markdown code fences if present before parsing.
    """
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return json.loads(text)
