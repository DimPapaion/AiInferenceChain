"""
InferenceNode — DNN Validator Node.

A full participant in the InferenceChain network:
  - Holds a cryptographic identity (keypair + address)
  - Loads and runs a CNN model for inference
  - Participates in QoI consensus rounds (PRE_PREPARE / PREPARE / COMMIT)
  - Participates in PoS rounds when no inference job is pending
  - Submits and responds to Proof of Model (PoM) challenges
  - Builds and signs transactions
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any

from core.blockchain.constants import (
    MIN_STAKE_DNN, NODE_TYPE_DNN,
    POM_CHALLENGE_SIZE, NUM_CLASSES,
)
from core.blockchain.transaction import (
    Transaction, TxType,
    NodeRegisterDNNPayload, ModelResponsePayload,
    StakePayload,
)
from core.blockchain.utils import now, sha256
from core.qoi.messages import (
    MsgType, PrePrepareMsg, PrepareMsg, CommitMsg,
    ViewChangeMsg, NewViewMsg, BaseMessage,
)
from core.qoi.state_machine import QoIStateMachine, QoIPhase, ConsensusOutcome
from core.qoi.pos_consensus import PoSConsensusMachine, PoSPhase, VoteMsg
from .identity import NodeIdentity


class NodeStatus(Enum):
    UNREGISTERED  = auto()   # not yet submitted NODE_REGISTER_DNN
    PENDING_POM   = auto()   # waiting for MODEL_CHALLENGE
    RESPONDING    = auto()   # responded to challenge, waiting for verifications
    ACTIVE        = auto()   # admitted, participating in consensus
    INACTIVE      = auto()   # slashed below MIN_STAKE or deactivated


@dataclass
class ModelHandle:
    """Thin wrapper around a loaded PyTorch model."""
    name:         str
    architecture: dict
    weights_path: str
    weights_hash: str
    dataset_id:   str
    _model:       Any = field(default=None, repr=False)

    def load(self) -> None:
        """Load model weights from disk."""
        try:
            import torch
            from models.model_registry import ModelRegistry
            registry = ModelRegistry(weights_dir=os.path.dirname(self.weights_path))
            self._model = registry.load(self.name, device="cpu")
        except Exception as e:
            raise RuntimeError(f"Failed to load model '{self.name}': {e}")

    def predict(self, image_tensor: Any) -> tuple[list[float], int]:
        """
        Run inference on a single image tensor.
        Returns (probabilities, predicted_class).
        """
        if self._model is None:
            self.load()
        try:
            from models.model_registry import ModelRegistry
            registry = ModelRegistry()
            probs, label = registry.infer(self._model, image_tensor)
            return probs.tolist(), int(label)
        except Exception as e:
            raise RuntimeError(f"Inference failed: {e}")

    def predict_batch(self, indices: list[int], dataset_id: str = "cifar10") -> list[int]:
        """
        Run inference on a list of dataset indices (for PoM challenge response).
        Returns list of predicted class indices.
        """
        if self._model is None:
            self.load()

        try:
            import torch
            import torchvision
            import torchvision.transforms as transforms

            transform = transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize(
                    (0.4914, 0.4822, 0.4465),
                    (0.2023, 0.1994, 0.2010)
                ),
            ])
            test_set = torchvision.datasets.CIFAR10(
                root="./data", train=False, download=True, transform=transform
            )
            predictions = []
            self._model.eval()
            with torch.no_grad():
                for idx in indices:
                    img, _ = test_set[idx]
                    img    = img.unsqueeze(0)
                    out    = self._model(img)
                    pred   = out.argmax(dim=1).item()
                    predictions.append(int(pred))
            return predictions

        except Exception as e:
            raise RuntimeError(f"Batch prediction failed: {e}")

    @staticmethod
    def compute_weights_hash(weights_path: str) -> str:
        """Compute SHA-256 of a weights file."""
        h = hashlib.sha256()
        with open(weights_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


class InferenceNode:
    """
    DNN Validator Node — participates in QoI consensus and PoS rounds.
    """

    def __init__(
        self,
        identity:    NodeIdentity,
        model:       ModelHandle,
        endpoint:    str,
        f:           int = 1,
    ) -> None:
        self.identity    = identity
        self.model       = model
        self.endpoint    = endpoint
        self.f           = f
        self.status      = NodeStatus.UNREGISTERED

        # Consensus state machines (set when round starts)
        self._qoi_sm:    Optional[QoIStateMachine]   = None
        self._pos_sm:    Optional[PoSConsensusMachine] = None

        # Nonce tracker (synced with chain state)
        self._nonce:     int = 0

    # ── Identity shortcuts ────────────────────────────────────────────────────

    @property
    def address(self) -> str:
        return self.identity.address

    @property
    def node_id(self) -> str:
        return self.identity.address

    # ── Registration ──────────────────────────────────────────────────────────

    def build_register_tx(self, fee: float = 1.0) -> Transaction:
        """Build and sign a NODE_REGISTER_DNN transaction."""
        self._nonce += 1
        tx = Transaction(
            tx_type = TxType.NODE_REGISTER_DNN,
            sender  = self.address,
            payload = NodeRegisterDNNPayload(
                model_name   = self.model.name,
                architecture = self.model.architecture,
                weights_hash = self.model.weights_hash,
                endpoint     = self.endpoint,
                dataset_id   = self.model.dataset_id,
                public_key   = self.identity.public_key_hex,
            ),
            nonce = self._nonce,
            fee   = fee,
        )
        tx.signature = self.identity.sign_tx(tx.tx_id)
        self.status  = NodeStatus.PENDING_POM
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

    # ── PoM challenge response ─────────────────────────────────────────────────

    def respond_to_challenge(
        self,
        challenge_tx: Transaction,
        fee:          float = 0.5,
    ) -> Transaction:
        """
        Respond to a MODEL_CHALLENGE by running the model on challenge samples.
        Returns a signed MODEL_RESPONSE tx.
        """
        challenge = challenge_tx.payload
        predictions = self.model.predict_batch(
            challenge.challenge_indices,
            challenge.dataset_id,
        )
        self._nonce += 1
        tx = Transaction(
            tx_type = TxType.MODEL_RESPONSE,
            sender  = self.address,
            payload = ModelResponsePayload(
                node_id     = self.node_id,
                predictions = predictions,
            ),
            nonce = self._nonce,
            fee   = fee,
        )
        tx.signature = self.identity.sign_tx(tx.tx_id)
        self.status  = NodeStatus.RESPONDING
        return tx

    # ── QoI consensus ─────────────────────────────────────────────────────────

    def start_qoi_round(
        self,
        request_id:   str,
        image_hash:   str,
        image_tensor: Any,
        seq:          int,
        primary_id:   str,
    ) -> Optional[PrePrepareMsg]:
        """
        Start a QoI round. If this node is primary, returns a PRE_PREPARE to broadcast.
        """
        probs, _ = self.model.predict(image_tensor)
        self._qoi_sm = QoIStateMachine(
            node_id    = self.node_id,
            primary_id = primary_id,
            f          = self.f,
        )
        msg = self._qoi_sm.start_round(request_id, image_hash, seq, probs)
        if msg:
            msg.signature = self.identity.sign(msg.to_dict())
        return msg

    def handle_qoi_message(self, msg: BaseMessage) -> Optional[BaseMessage]:
        """Feed an incoming QoI protocol message into the state machine."""
        if self._qoi_sm is None:
            return None
        response = self._qoi_sm.handle_message(msg)
        if response:
            response.signature = self.identity.sign(response.to_dict())
        return response

    def check_qoi_timeout(self, image_tensor: Any) -> Optional[ViewChangeMsg]:
        """Check for QoI round timeout and trigger view change if needed."""
        if self._qoi_sm is None:
            return None
        probs, _ = self.model.predict(image_tensor)
        vc = self._qoi_sm.check_timeout(probs)
        if vc:
            vc.signature = self.identity.sign(vc.to_dict())
        return vc

    @property
    def qoi_outcome(self) -> Optional[ConsensusOutcome]:
        return self._qoi_sm.outcome if self._qoi_sm else None

    @property
    def qoi_phase(self) -> Optional[QoIPhase]:
        return self._qoi_sm.phase if self._qoi_sm else None

    # ── PoS consensus ─────────────────────────────────────────────────────────

    def start_pos_round(self, proposer_id: str) -> None:
        """Initialise PoS state machine for this round."""
        self._pos_sm = PoSConsensusMachine(
            node_id     = self.node_id,
            proposer_id = proposer_id,
            f           = self.f,
        )

    def handle_pos_block(self, block: Any) -> Optional[VoteMsg]:
        """Handle a proposed PoS block — validate and return a signed vote."""
        if self._pos_sm is None:
            return None
        vote = self._pos_sm.handle_proposed_block(block)
        if vote:
            vote.signature = self.identity.sign(vote.to_dict())
        return vote

    def handle_pos_vote(self, vote: VoteMsg) -> bool:
        """Process an incoming PoS vote. Returns True if consensus reached."""
        if self._pos_sm is None:
            return False
        return self._pos_sm.handle_vote(vote)

    @property
    def pos_outcome(self):
        return self._pos_sm.outcome if self._pos_sm else None

    # ── Nonce sync ────────────────────────────────────────────────────────────

    def sync_nonce(self, chain_nonce: int) -> None:
        """Sync internal nonce counter with chain state."""
        self._nonce = chain_nonce

    def __repr__(self) -> str:
        return (
            f"InferenceNode(address={self.address[:8]}..., "
            f"model={self.model.name}, status={self.status.name})"
        )
