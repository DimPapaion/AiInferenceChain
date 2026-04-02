"""
Block definitions for InferenceChain.

Two block types:
  QOI — contains one InferenceRequest, runs QoI consensus
  POS — contains only simple transactions, runs PoS consensus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .transaction import Transaction, TxFamily
from .utils import sha256_json, compute_merkle_root


# ── Enums ─────────────────────────────────────────────────────────────────────

class BlockType(str, Enum):
    QOI = "qoi"     # inference block — QoI consensus
    POS = "pos"     # simple block   — PoS consensus


# ── Consensus Proof ───────────────────────────────────────────────────────────

@dataclass
class ConsensusProof:
    """
    Proof that 2f+1 nodes agreed on this block.
    Each entry in signatures is (node_id, signature_hex).
    """
    consensus_type: BlockType
    view:           int
    signatures:     list[tuple[str, str]] = field(default_factory=list)

    def is_valid(self, f: int) -> bool:
        """Check 2f+1 threshold."""
        return len(self.signatures) >= 2 * f + 1

    def add_signature(self, node_id: str, signature: str) -> None:
        # Prevent duplicate signatures from the same node
        existing = {s[0] for s in self.signatures}
        if node_id not in existing:
            self.signatures.append((node_id, signature))

    def to_dict(self) -> dict:
        return {
            "consensus_type": self.consensus_type.value,
            "view":           self.view,
            "signatures":     self.signatures,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ConsensusProof:
        return cls(
            consensus_type = BlockType(d["consensus_type"]),
            view           = d["view"],
            signatures     = [tuple(s) for s in d["signatures"]],
        )


# ── Block Header ──────────────────────────────────────────────────────────────

@dataclass
class BlockHeader:
    prev_hash:   str
    height:      int
    timestamp:   float
    proposer_id: str
    merkle_root: str
    block_type:  BlockType
    view:        int

    # Computed after all fields are set
    block_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.block_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        return sha256_json({
            "prev_hash":   self.prev_hash,
            "height":      self.height,
            "timestamp":   self.timestamp,
            "proposer_id": self.proposer_id,
            "merkle_root": self.merkle_root,
            "block_type":  self.block_type.value,
            "view":        self.view,
        })

    def to_dict(self) -> dict:
        return {
            "block_hash":  self.block_hash,
            "prev_hash":   self.prev_hash,
            "height":      self.height,
            "timestamp":   self.timestamp,
            "proposer_id": self.proposer_id,
            "merkle_root": self.merkle_root,
            "block_type":  self.block_type.value,
            "view":        self.view,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BlockHeader:
        header = cls(
            prev_hash   = d["prev_hash"],
            height      = d["height"],
            timestamp   = d["timestamp"],
            proposer_id = d["proposer_id"],
            merkle_root = d["merkle_root"],
            block_type  = BlockType(d["block_type"]),
            view        = d["view"],
        )
        return header


# ── Block ─────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    header:           BlockHeader
    simple_txs:       list[Transaction]
    consensus_proof:  ConsensusProof

    # Only present in QOI blocks
    inference_tx:  Optional[Transaction]       = None
    system_txs:    list[Transaction]           = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if self.header.block_type == BlockType.QOI:
            if self.inference_tx is None:
                raise ValueError("QOI block must contain an inference_tx.")
            if self.inference_tx.family != TxFamily.INFERENCE:
                raise ValueError("inference_tx must have INFERENCE family.")
        else:
            if self.inference_tx is not None:
                raise ValueError("POS block cannot contain an inference_tx.")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def hash(self) -> str:
        return self.header.block_hash

    @property
    def height(self) -> int:
        return self.header.height

    @property
    def all_transactions(self) -> list[Transaction]:
        """All transactions in canonical order: inference → simple → system."""
        txs: list[Transaction] = []
        if self.inference_tx:
            txs.append(self.inference_tx)
        txs.extend(self.simple_txs)
        txs.extend(self.system_txs)
        return txs

    @property
    def tx_count(self) -> int:
        return len(self.all_transactions)

    # ── Merkle ────────────────────────────────────────────────────────────────

    def compute_merkle_root(self) -> str:
        return compute_merkle_root(self.all_transactions)

    def verify_merkle_root(self) -> bool:
        return self.header.merkle_root == self.compute_merkle_root()

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "header":          self.header.to_dict(),
            "inference_tx":    self.inference_tx.to_dict() if self.inference_tx else None,
            "simple_txs":      [tx.to_dict() for tx in self.simple_txs],
            "system_txs":      [tx.to_dict() for tx in self.system_txs],
            "consensus_proof": self.consensus_proof.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Block:
        from .transaction import Transaction  # avoid circular at module level
        header = BlockHeader.from_dict(d["header"])
        inference_tx = (
            Transaction.from_dict(d["inference_tx"])
            if d.get("inference_tx") else None
        )
        simple_txs = [Transaction.from_dict(tx) for tx in d.get("simple_txs", [])]
        system_txs = [Transaction.from_dict(tx) for tx in d.get("system_txs", [])]
        proof      = ConsensusProof.from_dict(d["consensus_proof"])
        return cls(
            header          = header,
            simple_txs      = simple_txs,
            consensus_proof = proof,
            inference_tx    = inference_tx,
            system_txs      = system_txs,
        )

    def __repr__(self) -> str:
        return (
            f"Block(height={self.height}, type={self.header.block_type.value}, "
            f"txs={self.tx_count}, hash={self.hash[:8]}...)"
        )
