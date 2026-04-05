"""
OOD (Out-of-Distribution) Scoring for InferenceChain S-BFT Quorum Selection.

Implements the Knowledge Self-Assessment (KSA) module described in:
  Papaioannou et al. "A Decentralized Sharding BFT Consensus Approach,
  for Efficient Decentralized DNN Inference Classification" (ISCC 2024+)

Each DNN node must be able to score how familiar it is with a given image.
Nodes with low OOD scores (i.e., image looks In-Distribution to them) are
preferred for the quorum — they are more likely to produce accurate results.

Two scorers are provided, in order of accuracy vs. cost:

  1. MahalanobisOODScorer  [PRIMARY, recommended]
     Reuses the DNN's own penultimate-layer features. Computes class-
     conditional Gaussian statistics during a one-time calibration pass
     on the training/validation set. At inference time, scores a single
     image in one forward pass.

     Score = min_c  (z - μ_c)ᵀ Σ⁻¹ (z - μ_c)
     Lower = more In-Distribution (better node for the quorum).

  2. EnergyOODScorer  [LIGHTWEIGHT FALLBACK]
     Uses raw model logits. No calibration needed.

     Score = -log Σ_c exp(f_c(x))
     Lower = more In-Distribution.

  Both scorers expose the same interface:
    scorer.score(image_tensor) -> float   (lower = more ID)

  A NodeOODProfile records a node's calibrated scorer so that quorum.py
  can rank nodes without knowing which scorer they use internally.

  LikelihoodRegretScorer  [PAPER-EXACT, optional heavy path]
     VAE-based, exactly as in (Xiao et al. 2020).  Requires training a
     separate VAE per node and is significantly more expensive. Available
     for research/comparison but not the default.
"""

from __future__ import annotations

import hashlib
import math
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import logging
log = logging.getLogger(__name__)

# ── Lazy torch imports ────────────────────────────────────────────────────────

def _require_torch(caller: str) -> Any:
    try:
        import torch
        return torch
    except ImportError:
        raise ImportError(
            f"{caller} requires PyTorch. "
            "Install with: pip install torch torchvision"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Abstract base
# ═════════════════════════════════════════════════════════════════════════════

class OODScorer(ABC):
    """
    Abstract OOD scorer.

    Lower score  →  image is more In-Distribution  →  node is more suitable.
    Higher score →  image is more Out-of-Distribution → prefer other nodes.
    """

    @abstractmethod
    def score(self, image_tensor: Any) -> float:
        """
        Compute the OOD score for a single image tensor (C×H×W, float32).
        Returns a float; lower = more ID.
        """

    @abstractmethod
    def is_calibrated(self) -> bool:
        """True if the scorer has completed its calibration pass."""

    def name(self) -> str:
        return self.__class__.__name__


# ═════════════════════════════════════════════════════════════════════════════
# 1. Mahalanobis OOD Scorer  (primary)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class MahalanobisOODScorer(OODScorer):
    """
    Mahalanobis-distance OOD detector (Lee et al. 2018).

    Uses the DNN's penultimate-layer features:
      score(x) = min_c  (z - μ_c)ᵀ Σ⁻¹ (z - μ_c)

    where z = penultimate-layer embedding of x, μ_c = class-conditional mean,
    Σ = tied covariance across all classes (inverted once during calibration).

    Calibration:
        Call .calibrate(model, dataloader, device) once after the node is
        admitted. Takes O(N_calib * inference_time). Results are stored in
        _means, _inv_cov and can be serialised to disk.

    Usage:
        scorer = MahalanobisOODScorer()
        scorer.calibrate(model, calib_loader, device="cpu")
        s = scorer.score(image_tensor)   # float, lower = more ID
    """
    _means:   Optional[Any] = field(default=None, repr=False)  # (C, D) tensor
    _inv_cov: Optional[Any] = field(default=None, repr=False)  # (D, D) tensor
    _num_classes: int = 10

    def is_calibrated(self) -> bool:
        return self._means is not None and self._inv_cov is not None

    def calibrate(
        self,
        model:      Any,
        dataloader: Any,
        device:     str = "cpu",
        num_classes: int = 10,
    ) -> None:
        """
        Compute class-conditional means and tied inverse covariance from
        the model's penultimate layer over the calibration dataset.
        """
        torch = _require_torch("MahalanobisOODScorer.calibrate")
        model = model.to(device).eval()
        self._num_classes = num_classes

        features_by_class: dict[int, list] = {c: [] for c in range(num_classes)}

        hook_output: list[Any] = []

        def _hook(module, inp, out):
            hook_output.append(out.detach())

        # Register hook on the penultimate layer (before the final classifier)
        penultimate = _get_penultimate_layer(model)
        handle = penultimate.register_forward_hook(_hook)

        try:
            with torch.no_grad():
                for images, labels in dataloader:
                    images = images.to(device)
                    model(images)                     # triggers hook
                    batch_feats = hook_output[-1]     # (B, D) or (B, D, 1, 1)
                    if batch_feats.dim() > 2:
                        batch_feats = batch_feats.flatten(1)
                    hook_output.clear()
                    for feat, label in zip(batch_feats, labels):
                        features_by_class[int(label)].append(feat.cpu())
        finally:
            handle.remove()

        # Class-conditional means (C, D)
        means = []
        for c in range(num_classes):
            if features_by_class[c]:
                stacked = torch.stack(features_by_class[c])   # (N_c, D)
                means.append(stacked.mean(0))
            else:
                means.append(torch.zeros(features_by_class[0][0].shape))
        self._means = torch.stack(means)   # (C, D)

        # Tied covariance: pool all (z - μ_c) deviations
        D = self._means.shape[1]
        cov = torch.zeros(D, D)
        total = 0
        for c in range(num_classes):
            for feat in features_by_class[c]:
                diff = (feat - self._means[c]).unsqueeze(0)   # (1, D)
                cov += diff.T @ diff
                total += 1
        cov /= max(total - num_classes, 1)

        # Regularise before inversion (numerical stability)
        cov += 1e-6 * torch.eye(D)
        try:
            self._inv_cov = torch.linalg.inv(cov)
        except Exception:
            self._inv_cov = torch.eye(D)   # fallback identity
            log.warning("MahalanobisOODScorer: matrix inversion failed, using identity")

        log.info(
            "MahalanobisOODScorer calibrated: %d classes, feature_dim=%d, "
            "total_samples=%d",
            num_classes, D, total,
        )

    def score(self, image_tensor: Any) -> float:
        """
        Score a single image. Lower = more In-Distribution.
        Raises RuntimeError if not yet calibrated.
        """
        if not self.is_calibrated():
            raise RuntimeError(
                "MahalanobisOODScorer.score called before calibrate(). "
                "Run scorer.calibrate(model, dataloader) first."
            )
        torch = _require_torch("MahalanobisOODScorer.score")
        raise NotImplementedError(
            "score() requires access to the live model for a forward pass. "
            "Use score_with_model(model, image_tensor, device) instead."
        )

    def score_with_model(self, model: Any, image_tensor: Any, device: str = "cpu") -> float:
        """
        Score a single image using the provided model. Returns Mahalanobis distance.
        """
        if not self.is_calibrated():
            raise RuntimeError("Not calibrated.")
        torch = _require_torch("MahalanobisOODScorer.score_with_model")
        model = model.to(device).eval()

        hook_output: list[Any] = []

        def _hook(module, inp, out):
            hook_output.append(out.detach())

        penultimate = _get_penultimate_layer(model)
        handle = penultimate.register_forward_hook(_hook)
        try:
            with torch.no_grad():
                img = image_tensor.unsqueeze(0).to(device)
                model(img)
                z = hook_output[0]
                if z.dim() > 2:
                    z = z.flatten(1)
                z = z.cpu().squeeze(0)   # (D,)
        finally:
            handle.remove()

        # min_c  (z - μ_c)ᵀ Σ⁻¹ (z - μ_c)
        min_dist = float("inf")
        for c in range(self._num_classes):
            diff = z - self._means[c]                      # (D,)
            dist = float(diff @ self._inv_cov @ diff)
            if dist < min_dist:
                min_dist = dist
        return min_dist


# ═════════════════════════════════════════════════════════════════════════════
# 2. Energy OOD Scorer  (lightweight fallback)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class EnergyOODScorer(OODScorer):
    """
    Energy-based OOD detector (Liu et al. 2020).

    score(x) = -log Σ_c exp(f_c(x))

    No calibration needed — uses raw logits from a single forward pass.
    Less accurate than Mahalanobis but has zero setup cost.

    Lower score = more In-Distribution.
    """
    _model:  Optional[Any] = field(default=None, repr=False)
    _device: str = "cpu"

    def is_calibrated(self) -> bool:
        return self._model is not None

    def attach_model(self, model: Any, device: str = "cpu") -> None:
        """Attach the DNN model used for scoring."""
        self._model = model
        self._device = device

    def score(self, image_tensor: Any) -> float:
        if not self.is_calibrated():
            raise RuntimeError("EnergyOODScorer: no model attached. Call attach_model() first.")
        torch = _require_torch("EnergyOODScorer.score")
        model = self._model.to(self._device).eval()
        with torch.no_grad():
            img    = image_tensor.unsqueeze(0).to(self._device)
            logits = model(img).squeeze(0)   # (C,)
            energy = -torch.logsumexp(logits, dim=0).item()
        return energy


# ═════════════════════════════════════════════════════════════════════════════
# 3. Likelihood Regret Scorer  (paper-exact, heavy path)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class LikelihoodRegretScorer(OODScorer):
    """
    VAE-based Likelihood Regret OOD detector (Xiao et al. 2020).

    LR(x) = L(x; θ*, p̂(x)) - L(x; θ*, φ*)

    where L is the VAE ELBO:
      L(x; θ, φ) ≈ E_q[log p_θ(x|z)] - KL(q_φ(z|x) || p(z))

    Large LR → image is OOD (node is not familiar with this domain).
    Lower  LR → image is ID  (node has relevant training knowledge).

    This is the scorer described exactly in the paper. It requires:
      1. Training a VAE on the node's training data distribution.
      2. At test time, running a short per-sample optimisation to
         compute p̂(x) (the optimal posterior for that specific sample).

    Steps to use:
        scorer = LikelihoodRegretScorer()
        scorer.train_vae(train_dataloader, latent_dim=64, epochs=50)
        s = scorer.score(image_tensor)   # lower = more ID
    """
    _vae:       Optional[Any] = field(default=None, repr=False)
    _device:    str = "cpu"
    _latent_dim: int = 64
    _opt_steps:  int = 50    # gradient steps for per-sample posterior optimisation
    _opt_lr:     float = 0.01

    def is_calibrated(self) -> bool:
        return self._vae is not None

    def train_vae(
        self,
        dataloader: Any,
        latent_dim: int  = 64,
        epochs:     int  = 50,
        lr:         float = 1e-3,
        device:     str  = "cpu",
    ) -> None:
        """Train a small convolutional VAE on the node's training data."""
        torch = _require_torch("LikelihoodRegretScorer.train_vae")
        self._device    = device
        self._latent_dim = latent_dim

        vae = _build_vae(latent_dim).to(device)
        opt = torch.optim.Adam(vae.parameters(), lr=lr)

        vae.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            batches    = 0
            for images, _ in dataloader:
                images = images.to(device)
                recon, mu, log_var = vae(images)
                loss = _vae_elbo_loss(recon, images, mu, log_var)
                opt.zero_grad()
                loss.backward()
                opt.step()
                epoch_loss += loss.item()
                batches    += 1
            if (epoch + 1) % 10 == 0:
                log.info("LR-VAE epoch %d/%d  loss=%.4f", epoch + 1, epochs, epoch_loss / batches)

        self._vae = vae.eval()
        log.info("LikelihoodRegretScorer VAE trained (latent_dim=%d, epochs=%d)", latent_dim, epochs)

    def score(self, image_tensor: Any) -> float:
        """
        Compute Likelihood Regret for a single image.
        Lower = more In-Distribution.
        """
        if not self.is_calibrated():
            raise RuntimeError("LikelihoodRegretScorer: VAE not trained. Call train_vae() first.")
        torch = _require_torch("LikelihoodRegretScorer.score")

        vae    = self._vae.to(self._device)
        x      = image_tensor.unsqueeze(0).to(self._device)

        # ── L(x; θ*, φ*)  — standard ELBO under fixed encoder ────────────────
        with torch.no_grad():
            recon, mu, log_var = vae(x)
            base_elbo = -_vae_elbo_loss(recon, x, mu, log_var).item()

        # ── L(x; θ*, p̂(x))  — optimise posterior latent for this specific x ─
        # Freeze decoder; optimise a free latent q for this sample only
        z_opt = mu.clone().detach().requires_grad_(True)
        opt   = torch.optim.Adam([z_opt], lr=self._opt_lr)

        for _ in range(self._opt_steps):
            opt.zero_grad()
            recon_opt = vae.decode(z_opt)
            recon_loss = torch.nn.functional.mse_loss(recon_opt, x, reduction="sum")
            # KL towards standard normal: KL = 0.5 * ||z||²  (unit Gaussian prior)
            kl = 0.5 * (z_opt ** 2).sum()
            loss = recon_loss + kl
            loss.backward()
            opt.step()

        with torch.no_grad():
            recon_opt  = vae.decode(z_opt)
            opt_recon  = torch.nn.functional.mse_loss(recon_opt, x, reduction="sum").item()
            opt_kl     = 0.5 * float((z_opt ** 2).sum())
            opt_elbo   = -(opt_recon + opt_kl)

        lr_score = opt_elbo - base_elbo   # positive if x is OOD
        return float(lr_score)


# ═════════════════════════════════════════════════════════════════════════════
# Node OOD Profile — stored per DNN node, quorum.py reads it
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class NodeOODProfile:
    """
    Holds a node's OOD scorer and exposes a single .evaluate(image_tensor)
    method so quorum.py doesn't need to know which scorer is in use.

    The profile is built once during node admission (post-PoM) and reused
    for every subsequent quorum election.
    """
    node_id:      str
    scorer:       OODScorer
    model:        Optional[Any] = field(default=None, repr=False)
    device:       str = "cpu"
    dataset_id:   str = ""
    scorer_type:  str = field(init=False)

    def __post_init__(self):
        self.scorer_type = self.scorer.name()

    def evaluate(self, image_tensor: Any) -> float:
        """
        Return the OOD score for an image tensor.
        Lower = more In-Distribution = better candidate for quorum.
        """
        if isinstance(self.scorer, MahalanobisOODScorer):
            if self.model is None:
                raise RuntimeError(f"NodeOODProfile({self.node_id[:8]}): model not attached")
            return self.scorer.score_with_model(self.model, image_tensor, self.device)
        return self.scorer.score(image_tensor)

    def is_ready(self) -> bool:
        return self.scorer.is_calibrated()


# ═════════════════════════════════════════════════════════════════════════════
# OOD Profile Registry — global per-node store  (in-memory)
# ═════════════════════════════════════════════════════════════════════════════

class OODProfileRegistry:
    """
    Singleton-like registry mapping node_id → NodeOODProfile.

    The ConsensusEngine stores a profile here after a node passes PoM.
    quorum.py calls get_scores(image_tensor, node_ids) just before
    sampling to bias selection toward in-distribution nodes.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, NodeOODProfile] = {}

    def register(self, profile: NodeOODProfile) -> None:
        """Store or update the OOD profile for a node."""
        self._profiles[profile.node_id] = profile
        log.info(
            "OODProfileRegistry: registered %s (scorer=%s, dataset=%s)",
            profile.node_id[:12] + "…", profile.scorer_type, profile.dataset_id,
        )

    def get(self, node_id: str) -> Optional[NodeOODProfile]:
        return self._profiles.get(node_id)

    def score_nodes(
        self,
        node_ids:     list[str],
        image_tensor: Any,
    ) -> dict[str, float]:
        """
        Score each node in node_ids against image_tensor.
        Returns {node_id: ood_score} — nodes without a profile get score=+inf.
        """
        result: dict[str, float] = {}
        for nid in node_ids:
            profile = self._profiles.get(nid)
            if profile is None or not profile.is_ready():
                result[nid] = float("inf")   # unknown → treat as maximally OOD
            else:
                try:
                    result[nid] = profile.evaluate(image_tensor)
                except Exception as exc:
                    log.warning("OOD scoring failed for %s: %s", nid[:12], exc)
                    result[nid] = float("inf")
        return result

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._profiles


# ── Global registry instance ─────────────────────────────────────────────────
_global_ood_registry = OODProfileRegistry()


def get_ood_registry() -> OODProfileRegistry:
    """Return the process-global OOD profile registry."""
    return _global_ood_registry


# ═════════════════════════════════════════════════════════════════════════════
# Quorum scoring helper — called by quorum.py
# ═════════════════════════════════════════════════════════════════════════════

def rank_nodes_by_ood(
    node_ids:     list[str],
    image_tensor: Any,
    registry:     OODProfileRegistry | None = None,
) -> list[tuple[str, float]]:
    """
    Rank nodes by their OOD score for image_tensor.
    Returns [(node_id, score), ...] sorted ascending (lowest = most ID = preferred).

    Nodes not in the registry are pushed to the back with score=inf.
    """
    if registry is None:
        registry = get_ood_registry()
    scores = registry.score_nodes(node_ids, image_tensor)
    return sorted(scores.items(), key=lambda kv: kv[1])


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _get_penultimate_layer(model: Any) -> Any:
    """
    Return the penultimate layer of a model for hooking.
    Works for standard PyTorch Sequential and common CNN architectures.
    Falls back to the last module that is not the final Linear.
    """
    import torch.nn as nn
    children = list(model.children())

    # Typical architectures: last child is the classifier Linear
    # We want the layer just before it
    if children and isinstance(children[-1], nn.Linear):
        return children[-2] if len(children) >= 2 else children[-1]

    # ResNet-style: model.layer4 → model.avgpool → model.fc
    for attr in ("avgpool", "global_pool"):
        if hasattr(model, attr):
            return getattr(model, attr)

    # Fallback: last non-linear child
    for child in reversed(children):
        if not isinstance(child, nn.Linear):
            return child

    return children[-1]


def _build_vae(latent_dim: int = 64) -> Any:
    """
    Build a small convolutional VAE for 32×32 RGB images (CIFAR-10 sized).
    """
    import torch
    import torch.nn as nn

    class VAE(nn.Module):
        def __init__(self, latent_dim: int):
            super().__init__()
            self.latent_dim = latent_dim

            # Encoder: 3×32×32 → 512 → 2*latent_dim
            self.encoder = nn.Sequential(
                nn.Conv2d(3, 32, 4, 2, 1),   nn.ReLU(),    # 16×16
                nn.Conv2d(32, 64, 4, 2, 1),  nn.ReLU(),    # 8×8
                nn.Conv2d(64, 128, 4, 2, 1), nn.ReLU(),    # 4×4
                nn.Flatten(),
                nn.Linear(128 * 4 * 4, 512), nn.ReLU(),
            )
            self.fc_mu      = nn.Linear(512, latent_dim)
            self.fc_log_var = nn.Linear(512, latent_dim)

            # Decoder: latent_dim → 512 → 3×32×32
            self.decoder_fc = nn.Linear(latent_dim, 512)
            self.decoder = nn.Sequential(
                nn.Linear(512, 128 * 4 * 4), nn.ReLU(),
                nn.Unflatten(1, (128, 4, 4)),
                nn.ConvTranspose2d(128, 64, 4, 2, 1), nn.ReLU(),  # 8×8
                nn.ConvTranspose2d(64, 32, 4, 2, 1),  nn.ReLU(),  # 16×16
                nn.ConvTranspose2d(32,  3, 4, 2, 1),  nn.Sigmoid(), # 32×32
            )

        def encode(self, x):
            h       = self.encoder(x)
            mu      = self.fc_mu(h)
            log_var = self.fc_log_var(h)
            return mu, log_var

        def reparameterise(self, mu, log_var):
            import torch
            std = torch.exp(0.5 * log_var)
            eps = torch.randn_like(std)
            return mu + eps * std

        def decode(self, z):
            h = torch.relu(self.decoder_fc(z))
            return self.decoder(h)

        def forward(self, x):
            mu, log_var = self.encode(x)
            z           = self.reparameterise(mu, log_var)
            recon       = self.decode(z)
            return recon, mu, log_var

    return VAE(latent_dim)


def _vae_elbo_loss(recon: Any, x: Any, mu: Any, log_var: Any) -> Any:
    """
    Negative ELBO = reconstruction loss + KL divergence.
    Used both during VAE training and LR scoring.
    """
    import torch.nn.functional as F
    recon_loss = F.mse_loss(recon, x, reduction="sum")
    kl         = -0.5 * (1 + log_var - mu.pow(2) - log_var.exp()).sum()
    return recon_loss + kl
