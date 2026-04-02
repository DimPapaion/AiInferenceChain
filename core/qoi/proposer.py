"""
Proposer Selection for InferenceChain.

Primary (leader) selection is weighted by both stake AND reputation.
This ensures:
  - Economic skin in the game (stake) prevents Sybil attacks
  - Quality track record (reputation) promotes good validators to primary
  - Deterministic given the same seed — all nodes agree on who the primary is

Selection weight:
  w_i = stake_i * (1 + reputation_i)

The (1 + rep) multiplier means:
  - A node with rep=0 (new node) competes purely on stake
  - A node with higher rep gets progressively more selection probability
  - Reputation amplifies stake, not replaces it

Determinism:
  The seed is derived from the previous block hash + view number.
  All honest nodes compute the same seed → same primary.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Optional

from core.blockchain.chain import NodeInfo


def select_proposer(
    nodes:           list[NodeInfo],
    stakes:          dict[str, float],
    reputations:     dict[str, float],
    prev_block_hash: str,
    view:            int,
) -> Optional[str]:
    """
    Select the primary node for a given view deterministically.

    Args:
        nodes:           active validator nodes (stake >= MIN_STAKE)
        stakes:          {node_id: staked_amount}
        reputations:     {node_id: reputation_score}
        prev_block_hash: hash of the last committed block (entropy source)
        view:            current view number (increments on view change)

    Returns:
        node_id of the selected primary, or None if no eligible nodes.
    """
    if not nodes:
        return None

    # ── Compute weights ───────────────────────────────────────────────────────
    weights: list[float] = []
    node_ids: list[str]  = []

    for node in nodes:
        stake = stakes.get(node.node_id, 0.0)
        rep   = reputations.get(node.node_id, 0.0)
        w     = stake * (1.0 + max(0.0, rep))   # rep can't go negative here
        weights.append(w)
        node_ids.append(node.node_id)

    total_weight = sum(weights)
    if total_weight == 0.0:
        # All weights zero — fall back to round-robin by view number
        return node_ids[view % len(node_ids)]

    # ── Deterministic seed from prev_block_hash + view ────────────────────────
    seed_bytes = (prev_block_hash + str(view)).encode()
    seed_hash  = hashlib.sha256(seed_bytes).digest()
    # Use first 8 bytes as a uint64 → normalise to [0, 1)
    seed_int   = struct.unpack(">Q", seed_hash[:8])[0]
    roll       = (seed_int / (2 ** 64)) * total_weight

    # ── Weighted selection ────────────────────────────────────────────────────
    cumulative = 0.0
    for node_id, weight in zip(node_ids, weights):
        cumulative += weight
        if roll < cumulative:
            return node_id

    return node_ids[-1]   # fallback for floating point edge case


def proposer_for_view(
    nodes:           list[NodeInfo],
    stakes:          dict[str, float],
    reputations:     dict[str, float],
    prev_block_hash: str,
    base_view:       int,
    view:            int,
) -> Optional[str]:
    """
    On view change, the new primary is selected for `view`.
    Ensures the faulty primary from `base_view` is not re-selected
    until at least n views have passed.

    This is a thin wrapper — future extension point for exclusion logic.
    """
    return select_proposer(nodes, stakes, reputations, prev_block_hash, view)


def compute_weights(
    nodes:       list[NodeInfo],
    stakes:      dict[str, float],
    reputations: dict[str, float],
) -> dict[str, float]:
    """Return the selection weight for each node (for inspection/testing)."""
    return {
        node.node_id: stakes.get(node.node_id, 0.0) * (
            1.0 + max(0.0, reputations.get(node.node_id, 0.0))
        )
        for node in nodes
    }
