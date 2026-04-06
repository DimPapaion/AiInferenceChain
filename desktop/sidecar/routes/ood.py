from fastapi import APIRouter
from pydantic import BaseModel

import json
import time

from training.ood_profile import fit_profile_from_hf_dataset, score_knowledge_from_pil, decode_base64_image

router = APIRouter()


class OODFitRequest(BaseModel):
    dataset_name: str
    max_samples: int = 1024


class OODScoreRequest(BaseModel):
    profile: dict
    image_b64: str
    energy_score: float | None = None
    node_private_key_hex: str | None = None


@router.post("/fit")
def fit_ood_profile(req: OODFitRequest):
    """Fit a model-agnostic OOD familiarity profile from dataset images."""
    try:
        profile = fit_profile_from_hf_dataset(req.dataset_name, max_samples=req.max_samples)
        return {
            "ok": True,
            "profile": profile,
            "profile_hash": profile.get("profile_hash"),
            "method": profile.get("method"),
            "fitted_samples": profile.get("fitted_samples"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/score")
def score_ood(req: OODScoreRequest):
    """Compute per-image knowledge score K(x) from a fitted OOD profile."""
    try:
        img = decode_base64_image(req.image_b64)
        score = score_knowledge_from_pil(req.profile, img, energy_score=req.energy_score)

        payload = {
            "version": 1,
            "timestamp": int(time.time()),
            "profile_hash": req.profile.get("profile_hash"),
            **score,
        }

        signed = None
        if req.node_private_key_hex:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(req.node_private_key_hex))
            message = json.dumps(payload, sort_keys=True).encode("utf-8")
            sig = private_key.sign(message)
            pub = private_key.public_key().public_bytes_raw().hex()
            signed = {
                "payload": payload,
                "signature_hex": sig.hex(),
                "public_key_hex": pub,
            }

        return {
            "ok": True,
            **payload,
            "signed": signed,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
