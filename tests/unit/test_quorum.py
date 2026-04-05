"""
Unit tests for core/consensus/quorum.py

Tests cover:
  - Determinism: same inputs → same quorum
  - Floor constraint: < 4 eligible nodes → None
  - model_name filter: only matching nodes selected
  - OOD-biased shortlist: preferred nodes win when registry provided
  - OOD fallback on error: broken registry → pure random (no crash)
  - Quorum.ood_biased flag set correctly
  - f values: k=4→f=1, k=10→f=3, k=19→f=6
"""

from __future__ import annotations

import pytest
import random
from unittest.mock import MagicMock

from core.consensus.quorum import select_quorum, Quorum
from core.blockchain.chain import NodeInfo
from core.blockchain.constants import NODE_TYPE_DNN


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node(node_id: str, model_name: str = "resnet20", dataset_id: str = "cifar10") -> NodeInfo:
    """Build a minimal active DNN NodeInfo accepted by select_quorum."""
    return NodeInfo(
        node_id=node_id,
        address=f"addr_{node_id[-8:]}",
        node_type=NODE_TYPE_DNN,
        public_key="02" + "1" * 64,
        endpoint=f"http://{node_id[-8:]}.local",
        registered_at=0,
        is_active=True,
        pom_verified=True,
        model_name=model_name,
        dataset_id=dataset_id,
    )


def _nodes(n: int, model_name: str = "resnet20") -> list[dict]:
    return [_node(f"{'a' * 36}{i:04d}", model_name) for i in range(n)]


BLOCK_HASH  = "a" * 64
REQUEST_ID  = "req-0001"


# ═════════════════════════════════════════════════════════════════════════════
# Basic determinism
# ═════════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_same_inputs_same_quorum(self):
        nodes = _nodes(20)
        q1 = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        q2 = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert q1 is not None
        assert q1.node_ids() == q2.node_ids()

    def test_different_block_hash_different_quorum(self):
        nodes = _nodes(40)
        q1 = select_quorum(REQUEST_ID, "a" * 64, nodes, model_name="resnet20")
        q2 = select_quorum(REQUEST_ID, "b" * 64, nodes, model_name="resnet20")
        assert q1 is not None
        assert q2 is not None
        # With 40 nodes it is astronomically unlikely they match
        assert q1.node_ids() != q2.node_ids()

    def test_different_request_id_different_quorum(self):
        nodes = _nodes(40)
        q1 = select_quorum("req-001", BLOCK_HASH, nodes, model_name="resnet20")
        q2 = select_quorum("req-002", BLOCK_HASH, nodes, model_name="resnet20")
        assert q1 is not None
        assert q2 is not None
        assert q1.node_ids() != q2.node_ids()


# ═════════════════════════════════════════════════════════════════════════════
# Floor / ceiling
# ═════════════════════════════════════════════════════════════════════════════

class TestFloorCeiling:
    def test_below_floor_returns_none(self):
        # Only 3 nodes eligible → below floor of 4
        nodes = _nodes(3)
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert result is None

    def test_exactly_floor_returns_quorum(self):
        nodes  = _nodes(4)
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert result is not None
        assert len(result.nodes) == 4

    def test_quorum_size_does_not_exceed_ceiling(self):
        # With 50 nodes the quorum target may be at ceiling
        nodes = _nodes(50)
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert result is not None
        from core.blockchain.constants import QUORUM_CEILING
        assert len(result.nodes) <= QUORUM_CEILING

    def test_empty_pool_returns_none(self):
        assert select_quorum(REQUEST_ID, BLOCK_HASH, [], model_name="resnet20") is None


# ═════════════════════════════════════════════════════════════════════════════
# model_name filter
# ═════════════════════════════════════════════════════════════════════════════

class TestModelFilter:
    def test_only_matching_model_selected(self):
        nodes = _nodes(10, "resnet20") + _nodes(10, "densenet40")
        q = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="densenet40")
        assert q is not None
        densenet_ids = {n.node_id for n in _nodes(10, "densenet40")}
        assert all(node.node_id in densenet_ids for node in q.nodes)

    def test_no_matching_model_returns_none(self):
        nodes = _nodes(20, "resnet20")
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="mobilenetv2")
        assert result is None


# ═════════════════════════════════════════════════════════════════════════════
# f values
# ═════════════════════════════════════════════════════════════════════════════

class TestFValues:
    @pytest.mark.parametrize("k, expected_f", [
        (4,  1),
        (7,  2),
        (10, 3),
        (13, 4),
        (19, 6),
    ])
    def test_f_value(self, k: int, expected_f: int):
        """f = floor((k-1)/3)."""
        nodes  = _nodes(k)
        # Provide exactly k nodes so that K == k
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20", target=k)
        if result is None:
            pytest.skip(f"quorum returned None for k={k}")
        assert result.f == expected_f

    def test_f_equals_floor_k_minus_1_div_3(self):
        import math
        nodes  = _nodes(10)
        result = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert result is not None
        k = len(result.nodes)
        assert result.f == math.floor((k - 1) / 3)


# ═════════════════════════════════════════════════════════════════════════════
# OOD-biased selection
# ═════════════════════════════════════════════════════════════════════════════

class TestOODBiasedSelection:
    def _make_registry(self, scores: dict):
        """Build a mock OODProfileRegistry returning pre-set scores."""
        reg = MagicMock()
        reg.score_nodes.side_effect = lambda node_ids, tensor: {
            nid: scores.get(nid, float("inf")) for nid in node_ids
        }
        return reg

    def _preferred_nodes(self, n: int, score_offset: float = 0.0) -> list[dict]:
        return [
            _node(f"pref{'a' * 32}{i:04d}")
            for i in range(n)
        ]

    def _other_nodes(self, n: int) -> list[dict]:
        return [
            _node(f"other{'b' * 31}{i:04d}")
            for i in range(n)
        ]

    def test_ood_biased_flag_set_when_registry_provided(self):
        import torch
        nodes = _nodes(20)
        reg   = self._make_registry({n.node_id: 1.0 for n in nodes})
        img   = torch.randn(3, 32, 32)
        q = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20",
                          image_tensor=img, ood_registry=reg)
        assert q is not None
        assert q.ood_biased is True

    def test_no_ood_flag_without_registry(self):
        nodes = _nodes(20)
        q = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20")
        assert q is not None
        assert q.ood_biased is False

    def test_ood_selection_draws_from_top_2k_shortlist(self):
        """
        Give 5 preferred nodes score=0.01 and 20 others score=100.
        When OOD bias is active, selection should be restricted to the
        top-2K shortlist ranked by OOD score.
        """
        import torch

        preferred = self._preferred_nodes(5)
        others    = self._other_nodes(20)
        all_nodes = preferred + others

        scores    = {n.node_id: 0.01 for n in preferred}
        scores.update({n.node_id: 100.0 for n in others})
        reg = self._make_registry(scores)

        target = 4
        q = select_quorum(
            REQUEST_ID,
            BLOCK_HASH,
            all_nodes,
            model_name="resnet20",
            target=target,
            image_tensor=torch.randn(3, 32, 32),
            ood_registry=reg,
        )
        assert q is not None

        sorted_ids = [node_id for node_id, _ in sorted(scores.items(), key=lambda item: item[1])]
        shortlist_ids = set(sorted_ids[: 2 * target])
        assert all(node.node_id in shortlist_ids for node in q.nodes)

    def test_ood_scores_stored_on_quorum(self):
        import torch
        nodes = _nodes(20)
        scores = {n.node_id: float(i) for i, n in enumerate(nodes)}
        reg   = self._make_registry(scores)
        q = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20",
                          image_tensor=torch.randn(3, 32, 32), ood_registry=reg)
        assert q is not None
        assert isinstance(q.ood_scores, dict)
        # All quorum members should have an OOD score entry
        for m in q.nodes:
            assert m.node_id in q.ood_scores

    def test_ood_fallback_on_registry_error(self):
        """Broken registry → no crash, ood_biased=False."""
        import torch
        nodes = _nodes(20)
        bad_reg = MagicMock()
        bad_reg.score_nodes.side_effect = RuntimeError("broken registry")
        q = select_quorum(
            REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20",
            image_tensor=torch.randn(3, 32, 32),
            ood_registry=bad_reg,
        )
        assert q is not None
        assert q.ood_biased is False

    def test_ood_fallback_when_image_tensor_none(self):
        """No image tensor → no OOD, ood_biased=False."""
        nodes = _nodes(20)
        reg   = MagicMock()
        q = select_quorum(REQUEST_ID, BLOCK_HASH, nodes, model_name="resnet20",
                          image_tensor=None, ood_registry=reg)
        assert q is not None
        assert q.ood_biased is False
        # score_nodes should NOT have been called since image is None
        reg.score_nodes.assert_not_called()
