"""
S-BFT Quorum Selection for InferenceChain.

Problem solved:
  With N DNN nodes in the network (potentially thousands), running QoI
  across ALL of them for each inference request is unscalable:
    - O(N²) message complexity per round
    - Latency tracks the slowest node
    - Most nodes have no relevance to the specific model/dataset

Solution:
  For each inference request, elect a small quorum of K nodes (target=10,
  floor=4) from the eligible pool. The quorum is:
    1. Filtered to nodes whose model/dataset match the request
    2. Selected deterministically from that filtered pool using
       sha256(block_hash + request_id) as the seed — reproducible by
       any network participant, unpredictable before the request arrives

BFT parameters within the quorum:
  f = (quorum_size - 1) // 3
  required = 2f + 1

  quorum=4  → f=1, need 3
  quorum=7  → f=2, need 5
  quorum=10 → f=3, need 7
  quorum=13 → f=4, need 9
  quorum=19 → f=6, need 13
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from core.blockchain.chain import NodeInfo

# ── Tuneable constants ────────────────────────────────────────────────────────

QUORUM_TARGET  = 10   # ideal quorum size
QUORUM_FLOOR   = 4    # minimum size that still gives f=1 (need ≥3f+1)
QUORUM_CEILING = 19   # max quorum size (f=6, need 13 — generous for large nets)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Quorum:
    """
    A fully-resolved quorum for one inference request.

    Attributes
    ----------
    nodes        : ordered list of selected NodeInfo (order is deterministic)
    quorum_size  : len(nodes)
    f            : fault tolerance  = (quorum_size - 1) // 3
    threshold    : votes needed     = 2f + 1
    seed         : the hex seed used (for auditability / logging)
    """
    nodes:       tuple[NodeInfo, ...]
    quorum_size: int
    f:           int
    threshold:   int
    seed:        str

    def node_ids(self) -> frozenset[str]:
        return frozenset(n.node_id for n in self.nodes)

    def contains(self, node_id: str) -> bool:
        return node_id in self.node_ids()

    def __repr__(self) -> str:
        ids = ", ".join(n.node_id[:8] + "…" for n in self.nodes)
        return (
            f"Quorum(size={self.quorum_size}, f={self.f}, "
            f"threshold={self.threshold}, nodes=[{ids}])"
        )


# ── Quorum selection ─────────────────────────────────────────────────────────

def select_quorum(
    request_id:   str,
    block_hash:   str,
    eligible:     list[NodeInfo],
    model_name:   str | None = None,
    dataset_id:   str | None = None,
    target:       int        = QUORUM_TARGET,
    floor:        int        = QUORUM_FLOOR,
    ceiling:      int        = QUORUM_CEILING,
) -> Quorum | None:
    """
    Select a deterministic, verifiable quorum for one QoI round.

    Parameters
    ----------
    request_id   : unique ID of the inference request
    block_hash   : hash of the chain tip at the time of the request
    eligible     : all active DNN validators with stake ≥ MIN_STAKE_DNN
    model_name   : filter — only nodes running this model (None = no filter)
    dataset_id   : filter — only nodes trained on this dataset (None = no filter)
    target       : ideal quorum size
    floor        : minimum quorum size (below this, return None — too few nodes)
    ceiling      : cap on quorum size

    Returns
    -------
    Quorum  — the selected committee
    None    — not enough eligible nodes to form a viable quorum
    """
    # ── Filter by model/dataset ───────────────────────────────────────────────
    pool = _filter_eligible(eligible, model_name, dataset_id)

    if len(pool) < floor:
        return None   # network too sparse for this task

    # ── Seed: deterministic, unique per (block, request) ─────────────────────
    seed_input = (block_hash + request_id).encode()
    seed_hex   = hashlib.sha256(seed_input).hexdigest()
    seed_int   = int(seed_hex, 16)

    # ── Sample without replacement ────────────────────────────────────────────
    k   = min(max(floor, min(len(pool), target)), ceiling)
    rng = random.Random(seed_int)
    selected = rng.sample(pool, k)

    # Sort by node_id for a canonical, deterministic ordering
    selected.sort(key=lambda n: n.node_id)

    # ── BFT parameters ────────────────────────────────────────────────────────
    f         = (k - 1) // 3
    threshold = 2 * f + 1

    return Quorum(
        nodes       = tuple(selected),
        quorum_size = k,
        f           = f,
        threshold   = threshold,
        seed        = seed_hex,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _filter_eligible(
    nodes:      list[NodeInfo],
    model_name: str | None,
    dataset_id: str | None,
) -> list[NodeInfo]:
    """
    Return nodes whose model/dataset match the request.
    If no filter is given, all active DNN nodes are eligible.
    """
    result = []
    for n in nodes:
        if model_name and n.model_name != model_name:
            continue
        if dataset_id and n.dataset_id != dataset_id:
            continue
        result.append(n)
    return result


def quorum_f(quorum_size: int) -> int:
    """BFT fault tolerance for a given quorum size."""
    return (quorum_size - 1) // 3


def quorum_threshold(quorum_size: int) -> int:
    """Votes required for BFT commit in a quorum of given size."""
    return 2 * quorum_f(quorum_size) + 1
