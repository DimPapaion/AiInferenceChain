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
from dataclasses import dataclass, field
from typing import Any, Optional

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
    ood_scores   : {node_id: ood_score} if OOD-biased selection was used, else {}
    ood_biased   : True if quorum was selected using OOD scores (not purely random)
    """
    nodes:       tuple[NodeInfo, ...]
    quorum_size: int
    f:           int
    threshold:   int
    seed:        str
    ood_scores:  dict = field(default_factory=dict)
    ood_biased:  bool = False

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
    request_id:    str,
    block_hash:    str,
    eligible:      list[NodeInfo],
    model_name:    str | None        = None,
    dataset_id:    str | None        = None,
    target:        int               = QUORUM_TARGET,
    floor:         int               = QUORUM_FLOOR,
    ceiling:       int               = QUORUM_CEILING,
    image_tensor:  Any | None        = None,
    ood_registry:  Any | None        = None,
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
    image_tensor : if provided together with ood_registry, enables OOD-biased
                   selection — nodes most familiar with the image domain are
                   preferred. Determinism is preserved: OOD scores are used to
                   rank and stratify the pool; the seed breaks ties.
    ood_registry : OODProfileRegistry instance (from core.consensus.ood)

    Returns
    -------
    Quorum  — the selected committee
    None    — not enough eligible nodes to form a viable quorum
    """
    import logging
    log = logging.getLogger(__name__)

    # ── Filter by model/dataset ───────────────────────────────────────────────
    pool = _filter_eligible(eligible, model_name, dataset_id)

    if len(pool) < floor:
        return None   # network too sparse for this task

    # ── Seed: deterministic, unique per (block, request) ─────────────────────
    seed_input = (block_hash + request_id).encode()
    seed_hex   = hashlib.sha256(seed_input).hexdigest()
    seed_int   = int(seed_hex, 16)

    k         = min(max(floor, min(len(pool), target)), ceiling)
    ood_scores: dict[str, float] = {}
    ood_biased  = False

    # ── OOD-biased selection (when image_tensor + registry are available) ─────
    # Strategy: rank pool by OOD score (ascending = more in-distribution).
    # Take the top 2K nodes (or all if pool is small), then randomly sample K
    # from that shortlist using the deterministic seed. This gives:
    #   - bias toward in-distribution nodes (accuracy ↑)
    #   - maintained unpredictability (adversary can't exactly predict quorum)
    #   - full determinism (any node can reproduce the selection)
    if image_tensor is not None and ood_registry is not None:
        try:
            from core.consensus.ood import rank_nodes_by_ood
            node_ids   = [n.node_id for n in pool]
            ranked     = rank_nodes_by_ood(node_ids, image_tensor, ood_registry)
            ood_scores = {nid: sc for nid, sc in ranked}

            # Keep only nodes with finite scores (calibrated scorers)
            known  = [(nid, sc) for nid, sc in ranked if sc < float("inf")]
            unknown = [(nid, sc) for nid, sc in ranked if sc == float("inf")]

            # Build shortlist: top-2K of known nodes, padded with unknowns
            shortlist_ids = [nid for nid, _ in (known[:2 * k] + unknown)]
            id_to_node    = {n.node_id: n for n in pool}
            shortlist     = [id_to_node[nid] for nid in shortlist_ids if nid in id_to_node]

            if len(shortlist) >= floor:
                pool      = shortlist
                ood_biased = True
                log.debug(
                    "OOD-biased quorum: shortlisted %d/%d nodes (k=%d)",
                    len(shortlist), len(eligible), k,
                )
        except Exception as exc:
            log.warning("OOD quorum scoring failed, falling back to pure random: %s", exc)

    # ── Sample without replacement from pool ─────────────────────────────────
    rng      = random.Random(seed_int)
    selected = rng.sample(pool, min(k, len(pool)))

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
        ood_scores  = ood_scores,
        ood_biased  = ood_biased,
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
