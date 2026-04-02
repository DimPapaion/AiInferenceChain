"""
Utility functions for InferenceChain blockchain.
Merkle tree, hashing, and address derivation.
"""

import hashlib
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transaction import Transaction


# ── Hashing ───────────────────────────────────────────────────────────────────

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: dict) -> str:
    """Deterministic SHA-256 of a JSON-serialisable dict."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return sha256(raw)


def double_sha256(data: bytes) -> str:
    return sha256(hashlib.sha256(data).digest().hex().encode())


# ── Address ───────────────────────────────────────────────────────────────────

def pubkey_to_address(public_key_hex: str) -> str:
    """
    Derive a 20-byte (40 hex char) address from a public key.
    address = SHA-256(pubkey_bytes)[:20]
    Similar to Ethereum's keccak approach but using SHA-256.
    """
    raw = bytes.fromhex(public_key_hex)
    digest = hashlib.sha256(raw).digest()
    return digest[:20].hex()


def is_valid_address(address: str) -> bool:
    """Check if string is a valid 40-char hex address."""
    if len(address) != 40:
        return False
    try:
        bytes.fromhex(address)
        return True
    except ValueError:
        return False


# ── Merkle Tree ───────────────────────────────────────────────────────────────

def compute_merkle_root(transactions: list) -> str:
    """
    Compute Merkle root from a list of Transaction objects.
    Uses tx_id (already a SHA-256 hash) as leaf nodes.
    Returns SHA-256 of empty string for empty tx list.
    """
    if not transactions:
        return sha256(b"")

    hashes = [tx.tx_id for tx in transactions]
    return _merkle_from_hashes(hashes)


def compute_merkle_root_from_hashes(hashes: list[str]) -> str:
    if not hashes:
        return sha256(b"")
    return _merkle_from_hashes(list(hashes))


def _merkle_from_hashes(hashes: list[str]) -> str:
    while len(hashes) > 1:
        # Pad to even length by duplicating last element
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        hashes = [
            sha256((hashes[i] + hashes[i + 1]).encode())
            for i in range(0, len(hashes), 2)
        ]
    return hashes[0]


def verify_merkle_proof(tx_id: str, proof: list[tuple[str, str]], root: str) -> bool:
    """
    Verify a Merkle inclusion proof.
    proof: list of (sibling_hash, position) where position is 'left' or 'right'
    """
    current = tx_id
    for sibling, position in proof:
        if position == "left":
            combined = sibling + current
        else:
            combined = current + sibling
        current = sha256(combined.encode())
    return current == root


# ── Time ──────────────────────────────────────────────────────────────────────

def now() -> float:
    return time.time()


def now_ms() -> int:
    return int(time.time() * 1000)
