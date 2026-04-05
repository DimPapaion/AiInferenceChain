"""
Chain interaction routes — signing checkpoints and submitting to the network.
"""
import hashlib
import json
import time
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()

_sync_state = {
    "started_at": 0,
    "target_height": 0,
    "last_height": 0,
}


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


@router.get("/status")
def chain_status(endpoint: str = Query(default="http://localhost:8000")):
    """
    Check whether the InferenceChain node endpoint is reachable.
    Used by the UI to decide whether to show 'Submit' or 'Save for later'.
    """
    import requests as http_requests
    try:
        resp = http_requests.get(f"{endpoint}/health", timeout=5)
        reachable = resp.status_code == 200
    except Exception:
        reachable = False
    return {"reachable": reachable, "endpoint": endpoint}


@router.post("/sync/start")
def sync_start(endpoint: str = Query(default="http://localhost:8000")):
    """Mark sync start time and initialize internal sync state."""
    _sync_state["started_at"] = int(time.time())
    _sync_state["target_height"] = max(_sync_state["target_height"], _sync_state.get("last_height", 0))
    return {"ok": True, "endpoint": endpoint, "started_at": _sync_state["started_at"]}


@router.get("/sync/status")
def sync_status(endpoint: str = Query(default="http://localhost:8000")):
    """
    Fetch live sync-related status from the chain node endpoint.
    Returns peer count + height with step-style progress percentages.
    """
    import requests as http_requests

    reachable = False
    peer_count = 0
    chain_height = 0

    try:
        h = http_requests.get(f"{endpoint}/health", timeout=5)
        reachable = h.status_code == 200
    except Exception:
        reachable = False

    if reachable:
        try:
            p = http_requests.get(f"{endpoint}/p2p/status", timeout=5).json()
            peer_count = int(p.get("peer_count", 0) or 0)
            chain_height = int(p.get("chain_height", 0) or 0)
        except Exception:
            pass

        try:
            ch = http_requests.get(f"{endpoint}/chain/height", timeout=5).json()
            chain_height = max(chain_height, int(ch.get("height", 0) or 0))
        except Exception:
            pass

    _sync_state["last_height"] = max(_sync_state.get("last_height", 0), chain_height)
    _sync_state["target_height"] = max(_sync_state.get("target_height", 0), chain_height)

    target = max(_sync_state["target_height"], 1)
    progress_height = min(100, int((chain_height / target) * 100))
    progress_peers = 100 if peer_count >= 4 else min(100, peer_count * 25)

    # Split into two lanes to drive the UI exactly like a sync modal.
    consensus = [
        {"label": "Download checkpoint", "progress": 100 if chain_height > 0 else 5},
        {"label": "Find consensus peers", "progress": progress_peers},
        {"label": "Download slot data", "progress": progress_height},
    ]
    execution = [
        {"label": "Find execution peers", "progress": progress_peers},
        {"label": "Download state", "progress": progress_height},
        {"label": "Download block data", "progress": progress_height},
    ]

    return {
        "reachable": reachable,
        "endpoint": endpoint,
        "peer_count": peer_count,
        "chain_height": chain_height,
        "target_height": _sync_state["target_height"],
        "consensus": consensus,
        "execution": execution,
    }


@router.post("/save-manifest")
def save_manifest(req: SubmitRequest):
    """
    Save a signed manifest to disk (userData dir) so it can be submitted
    later when the chain is online.
    """
    import os
    save_dir = Path(os.environ.get("IC_DATA_DIR", Path.home() / ".inferencechain")) / "pending_submissions"
    save_dir.mkdir(parents=True, exist_ok=True)
    filename = f"manifest_{int(time.time())}.json"
    payload = {
        "manifest": req.manifest,
        "signature_hex": req.signature_hex,
        "node_public_key_hex": req.node_public_key_hex,
        "network_endpoint": req.network_endpoint,
        "saved_at": int(time.time()),
    }
    (save_dir / filename).write_text(json.dumps(payload, indent=2))
    return {"ok": True, "path": str(save_dir / filename)}


@router.get("/pending-submissions")
def list_pending():
    """List all locally saved manifests waiting to be submitted."""
    import os
    save_dir = Path(os.environ.get("IC_DATA_DIR", Path.home() / ".inferencechain")) / "pending_submissions"
    if not save_dir.exists():
        return {"items": []}
    items = []
    for f in sorted(save_dir.glob("manifest_*.json")):
        try:
            data = json.loads(f.read_text())
            items.append({"filename": f.name, "path": str(f), **data})
        except Exception:
            pass
    return {"items": items}
