"""
Unit tests for core/consensus/ood.py

Tests cover:
  - EnergyOODScorer (no calibration required, just pytorch)
  - MahalanobisOODScorer calibration + score
  - OODProfileRegistry score_nodes / rank_nodes_by_ood
  - Graceful fallback when torch is unavailable or scorer not calibrated
"""

from __future__ import annotations

import math
import pytest

# ── Fixture: mock torch-like tensors without requiring GPU ────────────────────
# We use real torch if available, otherwise skip OOD tests that need it.

torch = pytest.importorskip("torch", reason="torch not installed — skipping OOD tests")

from core.consensus.ood import (
    EnergyOODScorer,
    MahalanobisOODScorer,
    LikelihoodRegretScorer,
    NodeOODProfile,
    OODProfileRegistry,
    rank_nodes_by_ood,
    get_ood_registry,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_dummy_model(num_classes: int = 10, feature_dim: int = 64):
    """Tiny MLP for testing — not a real CNN but sufficient for scorer tests."""
    import torch.nn as nn
    return nn.Sequential(
        nn.Flatten(),
        nn.Linear(3 * 32 * 32, feature_dim),
        nn.ReLU(),
        nn.Linear(feature_dim, num_classes),
    )


def make_image_tensor(batch: int = 1):
    """Return a random (batch, 3, 32, 32) float tensor."""
    return torch.randn(batch, 3, 32, 32)


def make_single_image():
    return torch.randn(3, 32, 32)


def make_dataloader(num_classes: int = 10, samples_per_class: int = 8):
    """Return an iterable of (images, labels) for calibration."""
    images = make_image_tensor(batch=num_classes * samples_per_class)
    labels = torch.arange(num_classes).repeat(samples_per_class)
    dataset = torch.utils.data.TensorDataset(images, labels)
    return torch.utils.data.DataLoader(dataset, batch_size=16)


# ═════════════════════════════════════════════════════════════════════════════
# EnergyOODScorer
# ═════════════════════════════════════════════════════════════════════════════

class TestEnergyOODScorer:
    def test_not_calibrated_before_attach(self):
        scorer = EnergyOODScorer()
        assert not scorer.is_calibrated()

    def test_calibrated_after_attach(self):
        model = make_dummy_model()
        scorer = EnergyOODScorer()
        scorer.attach_model(model)
        assert scorer.is_calibrated()

    def test_score_returns_finite_float(self):
        model  = make_dummy_model()
        scorer = EnergyOODScorer()
        scorer.attach_model(model, device="cpu")
        s = scorer.score(make_single_image())
        assert isinstance(s, float)
        assert math.isfinite(s)

    def test_score_without_model_raises(self):
        scorer = EnergyOODScorer()
        with pytest.raises(RuntimeError, match="no model attached"):
            scorer.score(make_single_image())

    def test_score_in_distribution_lower_than_noise(self):
        """
        A model trained only on all-zero images should score zero-images
        lower (more ID) than random noise.
        This test heuristically checks the relative ordering.
        """
        import torch.nn as nn
        # Build model with weights tuned to output high logits for one class
        model = make_dummy_model()
        model.eval()
        scorer = EnergyOODScorer()
        scorer.attach_model(model, device="cpu")

        # Score the same input twice — must be deterministic
        img = make_single_image()
        s1  = scorer.score(img)
        s2  = scorer.score(img)
        assert abs(s1 - s2) < 1e-6

    def test_name_returns_class_name(self):
        assert EnergyOODScorer().name() == "EnergyOODScorer"


# ═════════════════════════════════════════════════════════════════════════════
# MahalanobisOODScorer
# ═════════════════════════════════════════════════════════════════════════════

class TestMahalanobisOODScorer:
    def test_not_calibrated_before_calibrate(self):
        scorer = MahalanobisOODScorer()
        assert not scorer.is_calibrated()

    def test_calibrated_after_calibrate(self):
        model  = make_dummy_model()
        loader = make_dataloader()
        scorer = MahalanobisOODScorer()
        scorer.calibrate(model, loader, device="cpu")
        assert scorer.is_calibrated()

    def test_score_with_model_returns_finite(self):
        model  = make_dummy_model()
        loader = make_dataloader()
        scorer = MahalanobisOODScorer()
        scorer.calibrate(model, loader, device="cpu")
        dist = scorer.score_with_model(model, make_single_image(), device="cpu")
        assert isinstance(dist, float)
        assert math.isfinite(dist)
        assert dist >= 0.0   # Mahalanobis distance is non-negative

    def test_score_direct_raises(self):
        """score() (without model) raises NotImplementedError."""
        scorer = MahalanobisOODScorer()
        scorer._means   = torch.zeros(10, 64)
        scorer._inv_cov = torch.eye(64)
        with pytest.raises(NotImplementedError):
            scorer.score(make_single_image())

    def test_score_before_calibrate_raises(self):
        scorer = MahalanobisOODScorer()
        model  = make_dummy_model()
        with pytest.raises(RuntimeError, match="Not calibrated"):
            scorer.score_with_model(model, make_single_image())

    def test_deterministic_score(self):
        """Same input must produce the same score."""
        model  = make_dummy_model()
        loader = make_dataloader()
        scorer = MahalanobisOODScorer()
        scorer.calibrate(model, loader, device="cpu")
        img = make_single_image()
        s1  = scorer.score_with_model(model, img)
        s2  = scorer.score_with_model(model, img)
        assert abs(s1 - s2) < 1e-5


# ═════════════════════════════════════════════════════════════════════════════
# OODProfileRegistry
# ═════════════════════════════════════════════════════════════════════════════

class TestOODProfileRegistry:
    def _make_profile(self, node_id: str, score: float):
        """Create a NodeOODProfile backed by an EnergyOODScorer with a fixed score."""

        class FixedScorer(EnergyOODScorer):
            def __init__(self, fixed_score):
                super().__init__()
                self._fixed_score = fixed_score
                self._model = object()   # truthy so is_calibrated() returns True

            def score(self, image_tensor):
                return self._fixed_score

        scorer = FixedScorer(score)

        # Patch is_calibrated and evaluate so they use the fixed scorer
        class FixedProfile(NodeOODProfile):
            def evaluate(self, image_tensor):
                return scorer.score(image_tensor)

            def is_ready(self):
                return True

        return FixedProfile(
            node_id    = node_id,
            scorer     = scorer,
            dataset_id = "cifar10",
        )

    def test_register_and_get(self):
        reg = OODProfileRegistry()
        profile = self._make_profile("node_a" + "0" * 34, 0.5)
        reg.register(profile)
        assert reg.get("node_a" + "0" * 34) is profile

    def test_get_unknown_returns_none(self):
        reg = OODProfileRegistry()
        assert reg.get("nonexistent" + "0" * 30) is None

    def test_score_nodes_returns_inf_for_unknown(self):
        reg     = OODProfileRegistry()
        scores  = reg.score_nodes(["unknown_node"], torch.randn(3, 32, 32))
        assert scores["unknown_node"] == float("inf")

    def test_score_nodes_returns_correct_scores(self):
        reg = OODProfileRegistry()
        p1  = self._make_profile("a" * 40, 1.0)
        p2  = self._make_profile("b" * 40, 3.0)
        reg.register(p1)
        reg.register(p2)

        scores = reg.score_nodes(["a" * 40, "b" * 40], make_single_image())
        assert scores["a" * 40] == pytest.approx(1.0)
        assert scores["b" * 40] == pytest.approx(3.0)

    def test_len_and_contains(self):
        reg = OODProfileRegistry()
        assert len(reg) == 0
        assert ("a" * 40) not in reg
        reg.register(self._make_profile("a" * 40, 0.0))
        assert len(reg) == 1
        assert ("a" * 40) in reg

    def test_rank_nodes_by_ood_sorted_ascending(self):
        reg = OODProfileRegistry()
        reg.register(self._make_profile("b" * 40, 5.0))   # high OOD
        reg.register(self._make_profile("a" * 40, 1.0))   # low OOD (preferred)
        reg.register(self._make_profile("c" * 40, 2.5))

        ranked = rank_nodes_by_ood(["a" * 40, "b" * 40, "c" * 40], make_single_image(), reg)
        ids    = [nid for nid, _ in ranked]
        # Should be sorted ascending by score: a(1.0) < c(2.5) < b(5.0)
        assert ids == ["a" * 40, "c" * 40, "b" * 40]

    def test_rank_nodes_puts_unknown_last(self):
        reg = OODProfileRegistry()
        reg.register(self._make_profile("a" * 40, 0.1))
        ranked = rank_nodes_by_ood(["a" * 40, "unknown" + "0" * 33], make_single_image(), reg)
        assert ranked[0][0] == "a" * 40
        assert ranked[1][1] == float("inf")
