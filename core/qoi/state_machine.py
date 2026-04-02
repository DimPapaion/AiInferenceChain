"""
QoI Consensus State Machine.

Implements PBFT adapted for DNN inference (QoI/PoQI protocol).

Phases per consensus round:
  IDLE         → waiting for an inference request
  PRE_PREPARE  → primary has broadcast its inference result
  PREPARE      → collecting PREPARE messages from replicas
  COMMIT       → 2f+1 PREPAREs seen, collecting COMMITs
  COMMITTED    → 2f+1 COMMITs seen, round complete
  VIEW_CHANGE  → suspected primary failure, collecting VIEW_CHANGEs

State machine is synchronous (single-threaded). Network layer feeds
messages in via handle_message(). Output is a ConsensusResult when
the COMMITTED state is reached.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from core.blockchain.constants import (
    DEFAULT_F, VIEW_CHANGE_TIMEOUT,
    INFERENCE_REWARD,
)
from core.blockchain.transaction import (
    Transaction, TxType,
    InferenceResponsePayload, ConsensusResultPayload,
    RewardPayload, SlashPayload,
)
from core.blockchain.utils import now

from .messages import (
    MsgType, BaseMessage,
    PrePrepareMsg, PrepareMsg, CommitMsg,
    ViewChangeMsg, NewViewMsg,
)
from .quality import compute_round_rewards, RoundResult


# ── States ────────────────────────────────────────────────────────────────────

class QoIPhase(Enum):
    IDLE         = auto()
    PRE_PREPARE  = auto()
    PREPARE      = auto()
    COMMIT       = auto()
    COMMITTED    = auto()
    VIEW_CHANGE  = auto()


# ── Consensus result ──────────────────────────────────────────────────────────

@dataclass
class ConsensusOutcome:
    """
    Produced when a round reaches COMMITTED.
    Contains everything needed to build the QoI block.
    """
    request_id:       str
    consensus_class:  int
    view:             int
    seq:              int
    primary_id:       str
    round_result:     RoundResult          # QoI scores, rewards, rep deltas
    commit_signatures: list[tuple[str, str]]  # (node_id, signature)

    def build_system_txs(
        self,
        block_proposer: str = "",
    ) -> list[Transaction]:
        """
        Convert this outcome into system transactions for the block:
          - One INFERENCE_RESPONSE per participating node
          - One CONSENSUS_RESULT
          - REWARD txs for honest nodes
          - SLASH txs for Byzantine nodes
        """
        txs: list[Transaction] = []
        genesis = "0" * 40
        nonce_counter = 1

        # INFERENCE_RESPONSE for each node
        for nr in self.round_result.node_results:
            txs.append(Transaction(
                tx_type   = TxType.INFERENCE_RESPONSE,
                sender    = nr.node_id,
                payload   = InferenceResponsePayload(
                    request_id      = self.request_id,
                    node_id         = nr.node_id,
                    probabilities   = nr.probabilities,
                    predicted_class = nr.predicted_class,
                ),
                nonce = nonce_counter,
                fee   = 0.0,
            ))
            nonce_counter += 1

        # CONSENSUS_RESULT
        participating = [nr.node_id for nr in self.round_result.node_results]
        txs.append(Transaction(
            tx_type = TxType.CONSENSUS_RESULT,
            sender  = genesis,
            payload = ConsensusResultPayload(
                request_id          = self.request_id,
                final_class         = self.consensus_class,
                confidence          = max(
                    (nr.qoi_score for nr in self.round_result.honest_nodes),
                    default=0.0,
                ),
                participating_nodes = participating,
            ),
            nonce = nonce_counter,
            fee   = 0.0,
        ))
        nonce_counter += 1

        # REWARD txs for honest nodes
        for nr in self.round_result.honest_nodes:
            if nr.token_reward > 0:
                txs.append(Transaction(
                    tx_type   = TxType.REWARD,
                    sender    = genesis,
                    recipient = nr.node_id,
                    payload   = RewardPayload(
                        amount     = nr.token_reward,
                        reason     = "honest_inference",
                        request_id = self.request_id,
                    ),
                    nonce = nonce_counter,
                    fee   = 0.0,
                ))
                nonce_counter += 1

        # SLASH txs for Byzantine nodes
        from core.blockchain.constants import SLASH_PENALTY
        for nr in self.round_result.byzantine_nodes:
            txs.append(Transaction(
                tx_type = TxType.SLASH,
                sender  = nr.node_id,
                payload = SlashPayload(
                    amount     = SLASH_PENALTY,
                    reason     = "byzantine_inference",
                    request_id = self.request_id,
                ),
                nonce = nonce_counter,
                fee   = 0.0,
            ))
            nonce_counter += 1

        return txs


# ── State machine ─────────────────────────────────────────────────────────────

class QoIStateMachine:
    """
    Per-node QoI consensus state machine.

    One instance per node. The node feeds incoming messages via
    handle_message() and calls check_timeout() periodically.

    When consensus is reached, outcome is stored in self.outcome.
    """

    def __init__(
        self,
        node_id:    str,
        primary_id: str,
        f:          int  = DEFAULT_F,
    ) -> None:
        self.node_id    = node_id
        self.primary_id = primary_id
        self.f          = f

        self.phase:   QoIPhase       = QoIPhase.IDLE
        self.view:    int            = 0
        self.seq:     int            = 0
        self.outcome: Optional[ConsensusOutcome] = None

        # Current round context
        self._request_id:  str   = ""
        self._image_hash:  str   = ""
        self._phase_start: float = 0.0

        # Message stores — keyed by (view, seq)
        self._pre_prepare:   Optional[PrePrepareMsg]        = None
        self._prepares:      dict[str, PrepareMsg]           = {}   # sender_id → msg
        self._commits:       dict[str, CommitMsg]            = {}   # sender_id → msg
        self._view_changes:  dict[str, ViewChangeMsg]        = {}   # sender_id → msg

        # Agreed consensus class after PREPARE quorum
        self._consensus_class: Optional[int] = None

        # Collected node responses for quality scoring
        # {node_id: (predicted_class, probabilities)}
        self._node_responses: dict[str, tuple[int, list[float]]] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    def is_primary(self) -> bool:
        return self.node_id == self.primary_id

    def start_round(
        self,
        request_id:      str,
        image_hash:      str,
        seq:             int,
        own_probs:       list[float],
    ) -> Optional[PrePrepareMsg]:
        """
        Start a new consensus round for a given inference request.
        If this node is the primary, returns a PRE_PREPARE message to broadcast.
        If replica, returns None (waits for PRE_PREPARE from primary).
        """
        self._reset_round(request_id, image_hash, seq)
        own_class = int(own_probs.index(max(own_probs)))

        # Record own response
        self._node_responses[self.node_id] = (own_class, list(own_probs))

        if self.is_primary():
            self.phase = QoIPhase.PRE_PREPARE
            msg = PrePrepareMsg(
                msg_type        = MsgType.PRE_PREPARE,
                view            = self.view,
                seq             = seq,
                sender_id       = self.node_id,
                request_id      = request_id,
                image_hash      = image_hash,
                probabilities   = list(own_probs),
                predicted_class = own_class,
            )
            self._pre_prepare = msg
            return msg

        self.phase = QoIPhase.PRE_PREPARE  # waiting for primary's PRE_PREPARE
        return None

    def handle_message(self, msg: BaseMessage) -> Optional[BaseMessage]:
        """
        Process an incoming protocol message.
        Returns a response message to broadcast, or None.

        Call flow:
          PRE_PREPARE received  → return PREPARE
          2f+1 PREPAREs         → return COMMIT
          2f+1 COMMITs          → set outcome, return None
          VIEW_CHANGE received  → if 2f+1, return NEW_VIEW (only new primary)
        """
        if msg.view < self.view:
            return None   # stale message, ignore

        match msg.msg_type:
            case MsgType.PRE_PREPARE:
                return self._handle_pre_prepare(msg)
            case MsgType.PREPARE:
                return self._handle_prepare(msg)
            case MsgType.COMMIT:
                return self._handle_commit(msg)
            case MsgType.VIEW_CHANGE:
                return self._handle_view_change(msg)
            case MsgType.NEW_VIEW:
                return self._handle_new_view(msg)
            case _:
                return None

    def check_timeout(self, own_probs: list[float]) -> Optional[ViewChangeMsg]:
        """
        Call this periodically. Returns a VIEW_CHANGE message if the
        current primary appears to be faulty (timeout exceeded).
        """
        if self.phase in (QoIPhase.IDLE, QoIPhase.COMMITTED):
            return None

        elapsed = now() - self._phase_start
        if elapsed > VIEW_CHANGE_TIMEOUT:
            return self._trigger_view_change()
        return None

    # ── Internal handlers ─────────────────────────────────────────────────────

    def _handle_pre_prepare(self, msg: PrePrepareMsg) -> Optional[PrepareMsg]:
        if self.phase != QoIPhase.PRE_PREPARE:
            return None
        if msg.sender_id != self.primary_id:
            return None   # only accept from known primary
        if msg.view != self.view or msg.seq != self.seq:
            return None

        self._pre_prepare = msg
        self._node_responses[msg.sender_id] = (
            msg.predicted_class, list(msg.probabilities)
        )
        self.phase = QoIPhase.PREPARE

        # Replica sends its own PREPARE with its own inference result
        own_class, own_probs = self._node_responses.get(
            self.node_id, (msg.predicted_class, msg.probabilities)
        )
        prepare = PrepareMsg(
            msg_type        = MsgType.PREPARE,
            view            = self.view,
            seq             = self.seq,
            sender_id       = self.node_id,
            request_id      = self._request_id,
            probabilities   = list(own_probs),
            predicted_class = own_class,
        )
        self._prepares[self.node_id] = prepare
        return prepare

    def _handle_prepare(self, msg: PrepareMsg) -> Optional[CommitMsg]:
        if self.phase not in (QoIPhase.PRE_PREPARE, QoIPhase.PREPARE):
            return None
        if msg.view != self.view or msg.seq != self.seq:
            return None
        if msg.sender_id in self._prepares:
            return None   # duplicate

        self._prepares[msg.sender_id] = msg
        self._node_responses[msg.sender_id] = (
            msg.predicted_class, list(msg.probabilities)
        )

        if len(self._prepares) < 2 * self.f + 1:
            return None   # not enough yet

        # Determine consensus class — majority among PREPAREs
        consensus_class = self._compute_consensus_class()
        if consensus_class is None:
            return None   # no majority yet

        self._consensus_class = consensus_class
        self.phase = QoIPhase.COMMIT

        commit = CommitMsg(
            msg_type        = MsgType.COMMIT,
            view            = self.view,
            seq             = self.seq,
            sender_id       = self.node_id,
            request_id      = self._request_id,
            consensus_class = consensus_class,
        )
        self._commits[self.node_id] = commit
        return commit

    def _handle_commit(self, msg: CommitMsg) -> None:
        if self.phase != QoIPhase.COMMIT:
            return None
        if msg.view != self.view or msg.seq != self.seq:
            return None
        if msg.sender_id in self._commits:
            return None   # duplicate
        if msg.consensus_class != self._consensus_class:
            return None   # conflicting commit — ignore

        self._commits[msg.sender_id] = msg

        if len(self._commits) < 2 * self.f + 1:
            return None

        # Reached 2f+1 COMMITs — round is complete
        self._finalise_round()
        return None

    def _handle_view_change(self, msg: ViewChangeMsg) -> Optional[NewViewMsg]:
        self._view_changes[msg.sender_id] = msg
        self.phase = QoIPhase.VIEW_CHANGE

        if len(self._view_changes) < 2 * self.f + 1:
            return None

        # New primary sends NEW_VIEW
        new_view = max(m.new_view for m in self._view_changes.values())
        new_primary = self._elect_new_primary(new_view)

        if new_primary != self.node_id:
            return None   # only the new primary broadcasts NEW_VIEW

        self.view      = new_view
        self.primary_id = new_primary
        self.phase     = QoIPhase.PRE_PREPARE

        return NewViewMsg(
            msg_type         = MsgType.NEW_VIEW,
            view             = self.view,
            seq              = self.seq,
            sender_id        = self.node_id,
            new_view         = new_view,
            view_change_msgs = [m.to_dict() for m in self._view_changes.values()],
        )

    def _handle_new_view(self, msg: NewViewMsg) -> None:
        if msg.new_view <= self.view:
            return None
        self.view       = msg.new_view
        self.primary_id = msg.sender_id
        self.phase      = QoIPhase.PRE_PREPARE
        self._view_changes.clear()
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _reset_round(self, request_id: str, image_hash: str, seq: int) -> None:
        self._request_id    = request_id
        self._image_hash    = image_hash
        self.seq            = seq
        self._phase_start   = now()
        self._pre_prepare   = None
        self._prepares      = {}
        self._commits       = {}
        self._view_changes  = {}
        self._consensus_class = None
        self._node_responses  = {}
        self.outcome          = None

    def _compute_consensus_class(self) -> Optional[int]:
        """
        Determine the consensus class from collected PREPAREs.
        Uses simple majority — the class with 2f+1 votes wins.
        """
        votes: dict[int, int] = defaultdict(int)
        for msg in self._prepares.values():
            votes[msg.predicted_class] += 1

        threshold = 2 * self.f + 1
        for cls, count in votes.items():
            if count >= threshold:
                return cls
        return None

    def _finalise_round(self) -> None:
        """Compute QoI rewards and build the ConsensusOutcome."""
        commit_sigs = [
            (node_id, msg.signature or "")
            for node_id, msg in self._commits.items()
        ]

        round_result = compute_round_rewards(
            request_id      = self._request_id,
            primary_id      = self.primary_id,
            consensus_class = self._consensus_class,
            node_responses  = self._node_responses,
            block_fees      = 0.0,   # injected by block builder
        )

        self.outcome = ConsensusOutcome(
            request_id        = self._request_id,
            consensus_class   = self._consensus_class,
            view              = self.view,
            seq               = self.seq,
            primary_id        = self.primary_id,
            round_result      = round_result,
            commit_signatures = commit_sigs,
        )
        self.phase = QoIPhase.COMMITTED

    def _trigger_view_change(self) -> ViewChangeMsg:
        self.phase = QoIPhase.VIEW_CHANGE
        return ViewChangeMsg(
            msg_type  = MsgType.VIEW_CHANGE,
            view      = self.view,
            seq       = self.seq,
            sender_id = self.node_id,
            new_view  = self.view + 1,
            last_seq  = self.seq,
        )

    def _elect_new_primary(self, new_view: int) -> str:
        """
        Deterministic new primary election from VIEW_CHANGE messages.
        Uses the sender with the highest last_seq (most up-to-date).
        Tie-break by node_id lexicographic order.
        """
        candidates = sorted(
            self._view_changes.values(),
            key=lambda m: (-m.last_seq, m.sender_id),
        )
        return candidates[0].sender_id if candidates else self.node_id
