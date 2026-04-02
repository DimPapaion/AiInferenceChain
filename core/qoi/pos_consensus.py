"""
PoS Consensus for simple blocks (no inference request pending).

Same BFT guarantee as QoI (2f+1), but simpler:
  1. Proposer selected (stake + reputation weighted)
  2. Proposer builds block from mempool simple txs
  3. All validators broadcast VOTE(block_hash, node_id, signature)
  4. 2f+1 votes → block committed

No inference, no QoI scoring, no reward pool split.
Proposer earns all block fees as reward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.constants import DEFAULT_F, VIEW_CHANGE_TIMEOUT
from core.blockchain.utils import now, sha256_json


# ── Vote message (internal, not a blockchain tx) ──────────────────────────────

@dataclass
class VoteMsg:
    node_id:    str
    block_hash: str
    view:       int
    signature:  str = ""
    timestamp:  float = field(default_factory=now)

    def to_dict(self) -> dict:
        return {
            "node_id":    self.node_id,
            "block_hash": self.block_hash,
            "view":       self.view,
            "signature":  self.signature,
            "timestamp":  self.timestamp,
        }


# ── States ────────────────────────────────────────────────────────────────────

class PoSPhase(Enum):
    IDLE      = auto()
    PROPOSED  = auto()   # waiting for votes on a proposed block
    COMMITTED = auto()
    VIEW_CHANGE = auto()


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class PoSOutcome:
    """Produced when a PoS round reaches 2f+1 votes."""
    block:      Block
    votes:      list[VoteMsg]
    proposer_id: str

    def consensus_proof(self) -> ConsensusProof:
        proof = ConsensusProof(
            consensus_type = BlockType.POS,
            view           = self.block.header.view,
        )
        for vote in self.votes:
            proof.add_signature(vote.node_id, vote.signature or "vote")
        return proof


# ── PoS State Machine ─────────────────────────────────────────────────────────

class PoSConsensusMachine:
    """
    Per-node PoS consensus state machine for simple (non-inference) blocks.
    """

    def __init__(
        self,
        node_id:     str,
        proposer_id: str,
        f:           int = DEFAULT_F,
    ) -> None:
        self.node_id     = node_id
        self.proposer_id = proposer_id
        self.f           = f

        self.phase:   PoSPhase        = PoSPhase.IDLE
        self.view:    int             = 0
        self.outcome: Optional[PoSOutcome] = None

        self._proposed_block: Optional[Block] = None
        self._votes:          dict[str, VoteMsg] = {}
        self._phase_start:    float = 0.0

    # ── Public interface ──────────────────────────────────────────────────────

    def is_proposer(self) -> bool:
        return self.node_id == self.proposer_id

    def propose_block(self, block: Block) -> VoteMsg:
        """
        Called by the proposer to announce a new block.
        Returns the proposer's own vote to broadcast.
        """
        self._proposed_block = block
        self.phase           = PoSPhase.PROPOSED
        self._phase_start    = now()
        self._votes          = {}

        vote = VoteMsg(
            node_id    = self.node_id,
            block_hash = block.hash,
            view       = self.view,
        )
        self._votes[self.node_id] = vote
        return vote

    def handle_proposed_block(self, block: Block) -> Optional[VoteMsg]:
        """
        Called by a replica when it receives a proposed block from the proposer.
        Validates the block and returns a vote if valid.
        """
        if not self._validate_proposed_block(block):
            return None

        self._proposed_block = block
        self.phase           = PoSPhase.PROPOSED
        self._phase_start    = now()

        vote = VoteMsg(
            node_id    = self.node_id,
            block_hash = block.hash,
            view       = self.view,
        )
        self._votes[self.node_id] = vote
        return vote

    def handle_vote(self, vote: VoteMsg) -> bool:
        """
        Process an incoming vote.
        Returns True if consensus has been reached (2f+1 votes).
        """
        if self._proposed_block is None:
            return False
        if vote.block_hash != self._proposed_block.hash:
            return False   # vote for a different block
        if vote.node_id in self._votes:
            return False   # duplicate

        self._votes[vote.node_id] = vote

        if len(self._votes) >= 2 * self.f + 1:
            self._finalise()
            return True

        return False

    def check_timeout(self) -> bool:
        """Returns True if timeout triggered (view change needed)."""
        if self.phase not in (PoSPhase.PROPOSED,):
            return False
        elapsed = now() - self._phase_start
        if elapsed > VIEW_CHANGE_TIMEOUT:
            self.phase = PoSPhase.VIEW_CHANGE
            self.view += 1
            return True
        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _validate_proposed_block(self, block: Block) -> bool:
        """Basic block validity check before voting."""
        if block.header.block_type != BlockType.POS:
            return False
        if block.inference_tx is not None:
            return False
        if not block.verify_merkle_root():
            return False
        return True

    def _finalise(self) -> None:
        self.outcome = PoSOutcome(
            block       = self._proposed_block,
            votes       = list(self._votes.values()),
            proposer_id = self.proposer_id,
        )
        self.phase = PoSPhase.COMMITTED
