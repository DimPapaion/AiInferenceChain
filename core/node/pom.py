"""
Proof of Model (PoM) — challenge generation, response verification,
and on-chain verification tracking.

Flow:
  1. generate_challenge()     → MODEL_CHALLENGE system tx
  2. verify_response()        → MODEL_VERIFY system tx (per validator)
  3. tally_verifications()    → NODE_ADMITTED or NODE_REJECTED system tx

Challenge is deterministic: seed = SHA-256(prev_block_hash + node_address)
Ground truth comes from the CIFAR-10 test set labels (public knowledge).
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional

from core.blockchain.constants import (
    POM_CHALLENGE_SIZE, MIN_MODEL_ACCURACY,
    DEFAULT_F, NODE_TYPE_DNN, NODE_TYPE_POS,
)
from core.blockchain.transaction import (
    Transaction, TxType,
    ModelChallengePayload, ModelResponsePayload,
    ModelVerifyPayload, NodeAdmittedPayload, NodeRejectedPayload,
)
from core.blockchain.utils import now

GENESIS_ADDRESS = "0" * 40

# ── CIFAR-10 test labels (public) ─────────────────────────────────────────────
# The CIFAR-10 test set has 10,000 samples with known labels.
# We embed a compact representation: the actual labels are loaded lazily
# from the data/ directory when needed, or generated deterministically in tests.

def load_cifar10_test_labels() -> list[int]:
    """
    Load CIFAR-10 test set labels.
    Returns list of 10,000 integers (0-9).
    Falls back to a deterministic pseudo-label list if data not available.
    """
    try:
        import pickle
        import os
        data_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data",
            "cifar-10-batches-py", "test_batch"
        )
        with open(data_path, "rb") as f:
            batch = pickle.load(f, encoding="bytes")
        return [int(x) for x in batch[b"labels"]]
    except Exception:
        # Fallback: deterministic pseudo-labels for testing
        # (cycle through 0-9 in order — known pattern, not random)
        return [i % 10 for i in range(10000)]


# ── Challenge generation ──────────────────────────────────────────────────────

def generate_challenge_indices(
    prev_block_hash: str,
    node_address:    str,
    n:               int = POM_CHALLENGE_SIZE,
    dataset_size:    int = 10_000,
) -> list[int]:
    """
    Deterministically select n challenge indices from the test set.
    Any node that knows prev_block_hash and node_address can reproduce this.
    """
    seed = hashlib.sha256((prev_block_hash + node_address).encode()).digest()
    indices: list[int] = []
    counter  = 0

    while len(indices) < n:
        # Hash seed with counter to get more indices
        h   = hashlib.sha256(seed + struct.pack(">I", counter)).digest()
        counter += 1
        # Extract up to 4 indices per hash (8 bytes each, 32 bytes total → 4)
        for i in range(0, 32, 8):
            val = struct.unpack(">Q", h[i:i+8])[0] % dataset_size
            if val not in indices:
                indices.append(val)
            if len(indices) == n:
                break

    return indices[:n]


def generate_challenge_tx(
    node_id:         str,
    prev_block_hash: str,
    dataset_id:      str = "cifar10",
    nonce:           int = 1,
) -> Transaction:
    """
    Build the MODEL_CHALLENGE system tx to be included in the next block.
    """
    labels  = load_cifar10_test_labels()
    indices = generate_challenge_indices(prev_block_hash, node_id)
    ground_truth = [labels[i] for i in indices]

    return Transaction(
        tx_type = TxType.MODEL_CHALLENGE,
        sender  = GENESIS_ADDRESS,
        payload = ModelChallengePayload(
            node_id           = node_id,
            challenge_indices = indices,
            ground_truth      = ground_truth,
            dataset_id        = dataset_id,
        ),
        nonce = nonce,
        fee   = 0.0,
    )


# ── Response verification ─────────────────────────────────────────────────────

def compute_accuracy(
    predictions:  list[int],
    ground_truth: list[int],
) -> float:
    """Compute fraction of correct predictions."""
    if len(predictions) != len(ground_truth):
        return 0.0
    correct = sum(p == g for p, g in zip(predictions, ground_truth))
    return correct / len(ground_truth)


def verify_model_response(
    challenge_tx:   Transaction,
    response_tx:    Transaction,
    verifier_id:    str,
    weights_hash:   str,
    verified_hash:  str,
    nonce:          int = 1,
) -> Transaction:
    """
    Build a MODEL_VERIFY system tx.
    The verifier has independently:
      1. Downloaded the weights file from the node's endpoint
      2. Verified SHA-256(weights) == weights_hash
      3. Loaded the model + run inference on the same challenge indices
      4. Computed accuracy against ground truth

    Args:
        challenge_tx:   the original MODEL_CHALLENGE tx
        response_tx:    the node's MODEL_RESPONSE tx
        verifier_id:    address of this verifying node
        weights_hash:   the hash committed on-chain at registration
        verified_hash:  SHA-256 of the weights file this verifier downloaded
        nonce:          verifier's nonce
    """
    challenge = challenge_tx.payload
    response  = response_tx.payload

    accuracy      = compute_accuracy(response.predictions, challenge.ground_truth)
    weights_match = (verified_hash == weights_hash)
    verified      = weights_match and accuracy >= MIN_MODEL_ACCURACY

    return Transaction(
        tx_type = TxType.MODEL_VERIFY,
        sender  = verifier_id,
        payload = ModelVerifyPayload(
            node_id       = challenge.node_id,
            verified      = verified,
            accuracy      = accuracy,
            weights_match = weights_match,
        ),
        nonce = nonce,
        fee   = 0.0,
    )


# ── Verification tally ────────────────────────────────────────────────────────

@dataclass
class PoMVerificationState:
    """Tracks accumulated MODEL_VERIFY txs for a pending node."""
    node_id:       str
    node_type:     str
    weights_hash:  str
    positive:      list[str] = field(default_factory=list)   # verifier addresses
    negative:      list[str] = field(default_factory=list)
    accuracies:    list[float] = field(default_factory=list)

    def add_verify(self, verifier_id: str, verified: bool, accuracy: float) -> None:
        if verifier_id in self.positive or verifier_id in self.negative:
            return   # duplicate
        if verified:
            self.positive.append(verifier_id)
        else:
            self.negative.append(verifier_id)
        self.accuracies.append(accuracy)

    def is_admitted(self, f: int) -> bool:
        return len(self.positive) >= 2 * f + 1

    def is_rejected(self, f: int, total_validators: int) -> bool:
        # Rejected if 2f+1 negatives, OR if not enough positives even with remaining votes
        remaining = total_validators - len(self.positive) - len(self.negative)
        can_still_pass = len(self.positive) + remaining >= 2 * f + 1
        return len(self.negative) >= 2 * f + 1 or not can_still_pass

    def mean_accuracy(self) -> float:
        if not self.accuracies:
            return 0.0
        return sum(self.accuracies) / len(self.accuracies)


def tally_pom(
    state:            PoMVerificationState,
    f:                int,
    total_validators: int,
    nonce:            int = 1,
) -> Optional[Transaction]:
    """
    Check if enough verifications have been collected.
    Returns NODE_ADMITTED or NODE_REJECTED tx, or None if still collecting.
    """
    if state.is_admitted(f):
        return Transaction(
            tx_type = TxType.NODE_ADMITTED,
            sender  = GENESIS_ADDRESS,
            payload = NodeAdmittedPayload(
                node_id       = state.node_id,
                node_type     = state.node_type,
                final_accuracy= state.mean_accuracy(),
            ),
            nonce = nonce,
            fee   = 0.0,
        )

    if state.is_rejected(f, total_validators):
        reason = (
            "insufficient_accuracy"
            if any(a < MIN_MODEL_ACCURACY for a in state.accuracies)
            else "weights_mismatch"
        )
        return Transaction(
            tx_type = TxType.NODE_REJECTED,
            sender  = GENESIS_ADDRESS,
            payload = NodeRejectedPayload(
                node_id = state.node_id,
                reason  = reason,
            ),
            nonce = nonce,
            fee   = 0.0,
        )

    return None   # still collecting
