"""
PoSNode — Stake-only Validator Node.

No DNN model. Participates only in PoS consensus rounds:
  - Proposes blocks (when selected as proposer)
  - Votes on proposed blocks
  - Earns block fees when proposer

Cannot participate in QoI rounds (no model).
Registration is simpler: no PoM required.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional, Any

from core.blockchain.constants import MIN_STAKE_POS, NODE_TYPE_POS
from core.blockchain.transaction import (
    Transaction, TxType,
    NodeRegisterPOSPayload, StakePayload,
)
from core.qoi.pos_consensus import PoSConsensusMachine, PoSOutcome, VoteMsg
from .identity import NodeIdentity


class PoSNodeStatus(Enum):
    UNREGISTERED = auto()
    PENDING      = auto()   # tx submitted, waiting to be mined
    ACTIVE       = auto()
    INACTIVE     = auto()


class PoSNode:
    """
    PoS-only validator node. Stakes INFER, proposes and votes on simple blocks.
    """

    def __init__(
        self,
        identity: NodeIdentity,
        endpoint: str,
        f:        int = 1,
    ) -> None:
        self.identity = identity
        self.endpoint = endpoint
        self.f        = f
        self.status   = PoSNodeStatus.UNREGISTERED
        self._pos_sm: Optional[PoSConsensusMachine] = None
        self._nonce:  int = 0

    # ── Identity shortcuts ────────────────────────────────────────────────────

    @property
    def address(self) -> str:
        return self.identity.address

    @property
    def node_id(self) -> str:
        return self.identity.address

    # ── Registration ──────────────────────────────────────────────────────────

    def build_register_tx(self, fee: float = 0.5) -> Transaction:
        """Build and sign a NODE_REGISTER_POS transaction."""
        self._nonce += 1
        tx = Transaction(
            tx_type = TxType.NODE_REGISTER_POS,
            sender  = self.address,
            payload = NodeRegisterPOSPayload(
                endpoint   = self.endpoint,
                public_key = self.identity.public_key_hex,
            ),
            nonce = self._nonce,
            fee   = fee,
        )
        tx.signature = self.identity.sign_tx(tx.tx_id)
        self.status  = PoSNodeStatus.PENDING
        return tx

    def build_stake_tx(self, amount: float, fee: float = 0.5) -> Transaction:
        """Build and sign a STAKE transaction."""
        self._nonce += 1
        tx = Transaction(
            tx_type = TxType.STAKE,
            sender  = self.address,
            payload = StakePayload(amount=amount),
            nonce   = self._nonce,
            fee     = fee,
        )
        tx.signature = self.identity.sign_tx(tx.tx_id)
        return tx

    # ── PoS consensus ─────────────────────────────────────────────────────────

    def start_pos_round(self, proposer_id: str) -> None:
        """Initialise PoS state machine for this round."""
        self._pos_sm = PoSConsensusMachine(
            node_id     = self.node_id,
            proposer_id = proposer_id,
            f           = self.f,
        )

    def is_proposer(self) -> bool:
        return self._pos_sm is not None and self._pos_sm.is_proposer()

    def propose_block(self, block: Any) -> VoteMsg:
        """Propose a block and return this node's vote."""
        if self._pos_sm is None:
            raise RuntimeError("PoS round not started — call start_pos_round() first")
        vote = self._pos_sm.propose_block(block)
        vote.signature = self.identity.sign(vote.to_dict())
        return vote

    def handle_proposed_block(self, block: Any) -> Optional[VoteMsg]:
        """Validate a proposed block and return a vote if valid."""
        if self._pos_sm is None:
            return None
        vote = self._pos_sm.handle_proposed_block(block)
        if vote:
            vote.signature = self.identity.sign(vote.to_dict())
        return vote

    def handle_vote(self, vote: VoteMsg) -> bool:
        """Process a vote. Returns True if consensus reached."""
        if self._pos_sm is None:
            return False
        return self._pos_sm.handle_vote(vote)

    def check_timeout(self) -> bool:
        """Returns True if timeout triggered."""
        if self._pos_sm is None:
            return False
        return self._pos_sm.check_timeout()

    @property
    def pos_outcome(self) -> Optional[PoSOutcome]:
        return self._pos_sm.outcome if self._pos_sm else None

    def sync_nonce(self, chain_nonce: int) -> None:
        self._nonce = chain_nonce

    def __repr__(self) -> str:
        return (
            f"PoSNode(address={self.address[:8]}..., "
            f"status={self.status.name})"
        )
