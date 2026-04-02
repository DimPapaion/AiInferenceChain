"""
QoI Quality Scoring and Reward/Slash computation.

Core math:
  QoI_i = cosine_similarity(p_i, p_agg)
  where p_agg = mean of probability vectors of honest nodes only
  (honest = argmax(p_i) == consensus_class)

Reward distribution:
  pool = block_fees + INFERENCE_REWARD (minted)
  weight_i  = QoI_i / sum(QoI_j for all honest j)
  reward_i  = pool * weight_i
  primary   gets additional LEADER_BONUS on top

Reputation:
  honest:   Δrep_i = min(QoI_i, REP_CAP_PER_ROUND)
  primary:  Δrep   += REP_LEADER_BONUS
  byzantine: rep   -= REP_PENALTY
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.blockchain.constants import (
    INFERENCE_REWARD, LEADER_BONUS,
    REP_CAP_PER_ROUND, REP_PENALTY, REP_LEADER_BONUS,
    QOI_HONEST_THRESHOLD,
)


# ── Cosine similarity ─────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Cosine similarity between two probability vectors.
    Returns value in [0, 1] for non-negative inputs (softmax outputs).
    Returns 0.0 if either vector is all-zero.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")

    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    # Clamp to [0, 1] — softmax outputs are non-negative so dot >= 0 always
    return min(1.0, max(0.0, dot / (norm_a * norm_b)))


def aggregate_probabilities(prob_vectors: list[list[float]]) -> list[float]:
    """
    Compute mean probability vector from a list of softmax outputs.
    Used to build the consensus reference vector for QoI scoring.
    Only honest nodes' vectors should be passed here.
    """
    if not prob_vectors:
        raise ValueError("Cannot aggregate empty probability list")

    n        = len(prob_vectors)
    n_classes = len(prob_vectors[0])
    agg      = [0.0] * n_classes

    for probs in prob_vectors:
        if len(probs) != n_classes:
            raise ValueError("Inconsistent probability vector lengths")
        for i, p in enumerate(probs):
            agg[i] += p

    return [x / n for x in agg]


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class NodeQoIResult:
    """QoI evaluation result for a single node in a consensus round."""
    node_id:         str
    is_honest:       bool
    predicted_class: int
    probabilities:   list[float]
    qoi_score:       float        # cosine similarity vs aggregated honest probs
    token_reward:    float        # INFER tokens earned this round
    rep_delta:       float        # reputation change this round


@dataclass
class RoundResult:
    """Full outcome of a QoI consensus round."""
    request_id:       str
    consensus_class:  int
    aggregated_probs: list[float]
    primary_id:       str
    node_results:     list[NodeQoIResult]
    total_pool:       float        # fees + minted reward

    @property
    def honest_nodes(self) -> list[NodeQoIResult]:
        return [r for r in self.node_results if r.is_honest]

    @property
    def byzantine_nodes(self) -> list[NodeQoIResult]:
        return [r for r in self.node_results if not r.is_honest]


# ── Main scoring function ─────────────────────────────────────────────────────

def compute_round_rewards(
    request_id:      str,
    primary_id:      str,
    consensus_class: int,
    node_responses:  dict[str, tuple[int, list[float]]],
    block_fees:      float = 0.0,
) -> RoundResult:
    """
    Compute QoI scores, token rewards, and reputation deltas for all nodes.

    Args:
        request_id:      the inference request ID
        primary_id:      node_id of the primary (leader) for this round
        consensus_class: the agreed argmax label (2f+1 agreement)
        node_responses:  {node_id: (predicted_class, probabilities)}
        block_fees:      total fees collected from simple txs in this block

    Returns:
        RoundResult with per-node rewards and reputation deltas.
    """
    total_pool = block_fees + INFERENCE_REWARD

    # ── Step 1: classify honest vs byzantine ─────────────────────────────────
    honest_probs:  list[list[float]] = []
    honest_ids:    list[str]         = []
    byzantine_ids: list[str]         = []

    for node_id, (pred_class, probs) in node_responses.items():
        if pred_class == consensus_class:
            honest_probs.append(probs)
            honest_ids.append(node_id)
        else:
            byzantine_ids.append(node_id)

    # ── Step 2: aggregate honest probs → reference vector ────────────────────
    if not honest_probs:
        # Edge case: all nodes were wrong — should not happen with valid consensus
        # but handle gracefully
        aggregated = [1.0 / len(node_responses)] * len(
            next(iter(node_responses.values()))[1]
        )
    else:
        aggregated = aggregate_probabilities(honest_probs)

    # ── Step 3: QoI score per honest node ────────────────────────────────────
    qoi_scores: dict[str, float] = {}
    for node_id in honest_ids:
        _, probs   = node_responses[node_id]
        score      = cosine_similarity(probs, aggregated)
        qoi_scores[node_id] = score

    # ── Step 4: token reward distribution ────────────────────────────────────
    qoi_sum = sum(qoi_scores.values())

    token_rewards: dict[str, float] = {}
    if qoi_sum > 0:
        for node_id, score in qoi_scores.items():
            token_rewards[node_id] = total_pool * (score / qoi_sum)
    else:
        # All QoI scores are 0 — equal split (degenerate case)
        share = total_pool / len(honest_ids) if honest_ids else 0.0
        for node_id in honest_ids:
            token_rewards[node_id] = share

    # Primary gets additional leader bonus
    if primary_id in token_rewards:
        token_rewards[primary_id] += LEADER_BONUS

    # ── Step 5: reputation deltas ─────────────────────────────────────────────
    rep_deltas: dict[str, float] = {}

    for node_id in honest_ids:
        delta = min(qoi_scores[node_id], REP_CAP_PER_ROUND)
        if node_id == primary_id:
            delta += REP_LEADER_BONUS
        rep_deltas[node_id] = delta

    for node_id in byzantine_ids:
        rep_deltas[node_id] = -REP_PENALTY

    # ── Step 6: build per-node results ────────────────────────────────────────
    node_results: list[NodeQoIResult] = []

    for node_id, (pred_class, probs) in node_responses.items():
        is_honest = node_id in honest_ids
        node_results.append(NodeQoIResult(
            node_id         = node_id,
            is_honest       = is_honest,
            predicted_class = pred_class,
            probabilities   = probs,
            qoi_score       = qoi_scores.get(node_id, 0.0),
            token_reward    = token_rewards.get(node_id, 0.0),
            rep_delta       = rep_deltas.get(node_id, 0.0),
        ))

    return RoundResult(
        request_id       = request_id,
        consensus_class  = consensus_class,
        aggregated_probs = aggregated,
        primary_id       = primary_id,
        node_results     = node_results,
        total_pool       = total_pool,
    )
