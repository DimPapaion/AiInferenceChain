"""
Hybrid OOD profile utilities for node familiarity scoring.

V2 approach:
- Shared frozen encoder embeddings (network-standardized)
- Class-conditional Mahalanobis-style distance profile
- Optional energy statistics from node classifier logits
- Fused knowledge score K(x)
"""

import base64
import json
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


METHOD_VERSION = "ood-hybrid-mahalanobis-energy-v2"
ENCODER_VERSION = "torchvision_vit_b_16_imagenet1k_v1"

_ENCODER = None


def _get_shared_encoder(device: torch.device):
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER

    import torchvision.models as models

    weights = models.ViT_B_16_Weights.IMAGENET1K_V1
    model = models.vit_b_16(weights=weights)
    model.heads = torch.nn.Identity()
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)

    _ENCODER = model.to(device)
    return _ENCODER


def _encode_batch(xb: torch.Tensor, encoder, device: torch.device) -> torch.Tensor:
    """Encode input tensors using shared frozen encoder and L2-normalize embeddings."""
    if xb.ndim != 4:
        raise ValueError("Expected input tensor with shape [B, C, H, W]")
    xb = xb.to(device)
    if xb.shape[-1] != 224 or xb.shape[-2] != 224:
        xb = F.interpolate(xb, size=(224, 224), mode="bilinear", align_corners=False)
    with torch.no_grad():
        z = encoder(xb)
        z = F.normalize(z, p=2, dim=1)
    return z.detach().cpu()


def _fit_diag_profile(features: torch.Tensor) -> dict:
    eps = 1e-6
    mu = features.mean(dim=0)
    var = features.var(dim=0, unbiased=False) + eps

    z = (features - mu) / torch.sqrt(var)
    d = torch.sum(z * z, dim=1)

    p90 = torch.quantile(d, 0.90).item()
    p95 = torch.quantile(d, 0.95).item()
    p99 = torch.quantile(d, 0.99).item()

    return {
        "mean": mu.tolist(),
        "var": var.tolist(),
        "distance_stats": {
            "mean": float(d.mean().item()),
            "std": float(d.std(unbiased=False).item()),
            "p90": float(p90),
            "p95": float(p95),
            "p99": float(p99),
        },
    }


def _collect_embeddings(loader, max_samples: int, device: torch.device) -> Tuple[torch.Tensor, torch.Tensor]:
    encoder = _get_shared_encoder(device)
    chunks: List[torch.Tensor] = []
    labels: List[torch.Tensor] = []
    count = 0
    for xb, yb in loader:
        emb = _encode_batch(xb, encoder, device)
        chunks.append(emb)
        labels.append(yb.detach().cpu())
        count += emb.shape[0]
        if count >= max_samples:
            break
    if not chunks:
        raise ValueError("No samples were available for OOD profile fitting.")
    all_emb = torch.cat(chunks, dim=0)[:max_samples]
    all_y = torch.cat(labels, dim=0)[:max_samples]
    return all_emb, all_y


def _collect_energy(model, loader, max_samples: int, device: torch.device, temperature: float = 1.0):
    energies = []
    count = 0
    model.eval()
    with torch.no_grad():
        for xb, _ in loader:
            xb = xb.to(device)
            logits = model(xb)
            e = -temperature * torch.logsumexp(logits / temperature, dim=1)
            energies.append(e.detach().cpu())
            count += e.shape[0]
            if count >= max_samples:
                break
    if not energies:
        return None
    out = torch.cat(energies, dim=0)[:max_samples]
    return {
        "mean": float(out.mean().item()),
        "std": float(out.std(unbiased=False).item()),
        "p10": float(torch.quantile(out, 0.10).item()),
        "p05": float(torch.quantile(out, 0.05).item()),
        "p01": float(torch.quantile(out, 0.01).item()),
        "temperature": float(temperature),
    }


def _fit_class_conditional_profile(embeddings: torch.Tensor, labels: torch.Tensor) -> dict:
    eps = 1e-6
    unique_labels = sorted(int(v) for v in labels.unique().tolist())
    by_class: Dict[str, dict] = {}
    all_min_dist = []

    for cls in unique_labels:
        mask = labels == cls
        cls_emb = embeddings[mask]
        if cls_emb.shape[0] < 2:
            continue
        mu = cls_emb.mean(dim=0)
        var = cls_emb.var(dim=0, unbiased=False) + eps
        by_class[str(cls)] = {
            "count": int(cls_emb.shape[0]),
            "mean": mu.tolist(),
            "var": var.tolist(),
        }

    if not by_class:
        # fallback to global single-class profile
        mu = embeddings.mean(dim=0)
        var = embeddings.var(dim=0, unbiased=False) + eps
        by_class = {
            "0": {
                "count": int(embeddings.shape[0]),
                "mean": mu.tolist(),
                "var": var.tolist(),
            }
        }

    for i in range(embeddings.shape[0]):
        x = embeddings[i]
        d_min = None
        for st in by_class.values():
            mu = torch.tensor(st["mean"], dtype=torch.float32)
            var = torch.tensor(st["var"], dtype=torch.float32)
            z = (x - mu) / torch.sqrt(var)
            d = float(torch.sum(z * z).item())
            d_min = d if d_min is None else min(d_min, d)
        all_min_dist.append(d_min if d_min is not None else 0.0)

    d = torch.tensor(all_min_dist, dtype=torch.float32)
    distance_stats = {
        "mean": float(d.mean().item()),
        "std": float(d.std(unbiased=False).item()),
        "p90": float(torch.quantile(d, 0.90).item()),
        "p95": float(torch.quantile(d, 0.95).item()),
        "p99": float(torch.quantile(d, 0.99).item()),
    }

    return {
        "class_stats": by_class,
        "distance_stats": distance_stats,
    }


def _sha256_json(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def fit_profile_from_loaders(
    train_loader,
    val_loader=None,
    model: Optional[torch.nn.Module] = None,
    device: Optional[torch.device] = None,
    max_samples: int = 2048,
) -> dict:
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_emb, train_y = _collect_embeddings(train_loader, max_samples=max_samples, device=device)
    domain_profile = _fit_class_conditional_profile(train_emb, train_y)

    energy_profile = None
    if model is not None:
        target_loader = val_loader if val_loader is not None else train_loader
        energy_profile = _collect_energy(model, target_loader, max_samples=max_samples, device=device)

    profile = {
        "version": 1,
        "method": METHOD_VERSION,
        "encoder": {
            "name": ENCODER_VERSION,
            "embedding_dim": int(train_emb.shape[1]),
            "input_size": [3, 224, 224],
        },
        "fitted_samples": int(train_emb.shape[0]),
        "feature_dim": int(train_emb.shape[1]),
        "domain_profile": domain_profile,
        "energy_profile": energy_profile,
        "fusion": {
            "w_embed": 1.0,
            "w_energy": 0.35,
            "b": 0.0,
            "sigma": "sigmoid",
        },
    }
    profile["profile_hash"] = _sha256_json(profile)
    return profile


def save_profile(profile: dict, output_path: str) -> Tuple[str, str]:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return str(out), profile.get("profile_hash", "")


def fit_profile_from_hf_dataset(dataset_name: str, max_samples: int = 1024) -> dict:
    from datasets import load_dataset

    raw = load_dataset(dataset_name)
    split = raw.get("train") or raw[list(raw.keys())[0]]

    img_key = "image"
    if img_key not in split.features:
        if "img" in split.features:
            img_key = "img"
        else:
            raise ValueError("Could not find image feature key (expected 'image' or 'img').")

    label_key = "label" if "label" in split.features else ("fine_label" if "fine_label" in split.features else None)
    encoder = _get_shared_encoder(torch.device("cuda" if torch.cuda.is_available() else "cpu"))

    features = []
    labels = []
    for i, item in enumerate(split):
        if i >= max_samples:
            break
        img = item[img_key]
        if not isinstance(img, Image.Image):
            img = Image.fromarray(img)
        arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
        t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
        feat = _encode_batch(t, encoder, next(encoder.parameters()).device).squeeze(0)
        features.append(feat)
        labels.append(int(item[label_key]) if label_key else 0)

    if not features:
        raise ValueError("No images found while fitting OOD profile.")

    all_feats = torch.stack(features, dim=0)
    all_labels = torch.tensor(labels, dtype=torch.long)
    domain_profile = _fit_class_conditional_profile(all_feats, all_labels)

    profile = {
        "version": 1,
        "method": METHOD_VERSION,
        "encoder": {
            "name": ENCODER_VERSION,
            "embedding_dim": int(all_feats.shape[1]),
            "input_size": [3, 224, 224],
        },
        "fitted_samples": int(all_feats.shape[0]),
        "feature_dim": int(all_feats.shape[1]),
        "domain_profile": domain_profile,
        "energy_profile": None,
        "dataset_name": dataset_name,
        "fusion": {
            "w_embed": 1.0,
            "w_energy": 0.35,
            "b": 0.0,
            "sigma": "sigmoid",
        },
    }
    profile["profile_hash"] = _sha256_json(profile)
    return profile


def score_knowledge_from_pil(profile: dict, image: Image.Image, energy_score: Optional[float] = None) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = _get_shared_encoder(device)

    arr = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
    emb = _encode_batch(t, encoder, device).squeeze(0)

    by_class = profile.get("domain_profile", {}).get("class_stats", {})
    if not by_class:
        raise ValueError("Profile missing class_stats.")

    best = None
    best_cls = None
    for cls, st in by_class.items():
        mu = torch.tensor(st["mean"], dtype=torch.float32)
        var = torch.tensor(st["var"], dtype=torch.float32)
        z = (emb - mu) / torch.sqrt(var)
        d = float(torch.sum(z * z).item())
        if best is None or d < best:
            best = d
            best_cls = cls

    dist_stats = profile.get("domain_profile", {}).get("distance_stats", {})
    d_mean = float(dist_stats.get("mean", 0.0))
    d_std = float(dist_stats.get("std", 1.0)) or 1.0

    # Higher is more familiar
    s_embed = -(best - d_mean) / d_std

    s_energy = 0.0
    energy_profile = profile.get("energy_profile")
    if energy_score is not None and energy_profile is not None:
        e_mean = float(energy_profile.get("mean", 0.0))
        e_std = float(energy_profile.get("std", 1.0)) or 1.0
        s_energy = -(float(energy_score) - e_mean) / e_std

    fusion = profile.get("fusion", {})
    w1 = float(fusion.get("w_embed", 1.0))
    w2 = float(fusion.get("w_energy", 0.35))
    b = float(fusion.get("b", 0.0))
    z = w1 * s_embed + w2 * s_energy + b
    k = 1.0 / (1.0 + float(np.exp(-z)))

    return {
        "knowledge_score": float(k),
        "predicted_cluster": best_cls,
        "distance": float(best),
        "embed_score": float(s_embed),
        "energy_score_norm": float(s_energy),
    }


def decode_base64_image(image_b64: str) -> Image.Image:
    data = base64.b64decode(image_b64)
    return Image.open(BytesIO(data)).convert("RGB")
