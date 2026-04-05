"""
Chain interaction routes — signing checkpoints and submitting to the network.
"""
import hashlib
import json
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class SignRequest(BaseModel):
    checkpoint_path: str
    arch_hash: str
    dataset_hash: str
    config: dict
    metrics: list
    node_private_key_hex: str  # hex-encoded 32-byte private key


class SubmitRequest(BaseModel):
    manifest: dict
    signature_hex: str
    node_public_key_hex: str
    network_endpoint: str = "http://localhost:8000"


@router.post("/sign-checkpoint")
def sign_checkpoint(req: SignRequest):
    """
    Build a training manifest and sign it with the node's private key.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        if not Path(req.checkpoint_path).is_file():
            return {"ok": False, "error": "Checkpoint file not found."}

        # Hash the checkpoint file
        ckpt_hash = _sha256_file(req.checkpoint_path)

        manifest = {
            "version": 1,
            "timestamp": int(time.time()),
            "arch_hash": req.arch_hash,
            "dataset_hash": req.dataset_hash,
            "checkpoint_hash": ckpt_hash,
            "config": req.config,
            "final_metrics": req.metrics[-1] if req.metrics else {},
        }

        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()

        # Accept both raw hex and PEM; assume raw hex 32-byte seed
        key_bytes = bytes.fromhex(req.node_private_key_hex)
        private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
        signature = private_key.sign(manifest_bytes)
        public_key = private_key.public_key()
        public_bytes = public_key.public_bytes_raw()

        return {
            "ok": True,
            "manifest": manifest,
            "signature_hex": signature.hex(),
            "public_key_hex": public_bytes.hex(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/submit")
def submit_to_network(req: SubmitRequest):
    """
    POST the signed manifest to the InferenceChain node endpoint.
    """
    import requests as http_requests
    try:
        payload = {
            "manifest": req.manifest,
            "signature": req.signature_hex,
            "public_key": req.node_public_key_hex,
        }
        resp = http_requests.post(
            f"{req.network_endpoint}/api/node/register",
            json=payload,
            timeout=30,
        )
        return {"ok": resp.status_code == 200, "response": resp.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
