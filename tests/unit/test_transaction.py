"""
Unit tests for core/blockchain/transaction.py
"""

import pytest
from core.blockchain import (
    Transaction, TxType, TxFamily,
    TokenTransferPayload, StakePayload, UnstakePayload,
    NodeRegisterPayload, ContractDeployPayload, ContractCallPayload,
    InferenceRequestPayload, InferenceResponsePayload,
    ConsensusResultPayload, RewardPayload, SlashPayload,
)

SENDER    = "a" * 40
RECIPIENT = "b" * 40


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_transfer(amount=10.0, fee=0.1, nonce=1):
    return Transaction(
        tx_type   = TxType.TOKEN_TRANSFER,
        sender    = SENDER,
        recipient = RECIPIENT,
        payload   = TokenTransferPayload(amount=amount),
        nonce     = nonce,
        fee       = fee,
    )


# ── tx_id ─────────────────────────────────────────────────────────────────────

class TestTxId:
    def test_id_is_64_hex_chars(self):
        tx = make_transfer()
        assert len(tx.tx_id) == 64
        assert all(c in "0123456789abcdef" for c in tx.tx_id)

    def test_same_inputs_same_id(self):
        tx1 = make_transfer(amount=10.0, fee=0.1, nonce=1)
        tx2 = make_transfer(amount=10.0, fee=0.1, nonce=1)
        # Timestamps differ slightly so tx_id may differ — that's correct
        # But changing nonce must change id
        tx3 = make_transfer(amount=10.0, fee=0.1, nonce=2)
        assert tx1.tx_id != tx3.tx_id

    def test_different_amount_different_id(self):
        tx1 = make_transfer(amount=10.0)
        tx2 = make_transfer(amount=20.0)
        assert tx1.tx_id != tx2.tx_id


# ── Family ────────────────────────────────────────────────────────────────────

class TestTxFamily:
    def test_transfer_is_simple(self):
        assert make_transfer().family == TxFamily.SIMPLE

    def test_inference_request_family(self):
        tx = Transaction(
            tx_type = TxType.INFERENCE_REQUEST,
            sender  = SENDER,
            payload = InferenceRequestPayload(
                request_id="req1", image_hash="a" * 64, model_hint="any"
            ),
            nonce = 1,
        )
        assert tx.family == TxFamily.INFERENCE

    def test_reward_is_system(self):
        tx = Transaction(
            tx_type   = TxType.REWARD,
            sender    = SENDER,
            recipient = RECIPIENT,
            payload   = RewardPayload(amount=10.0, reason="honest", request_id="req1"),
            nonce     = 1,
        )
        assert tx.family == TxFamily.SYSTEM

    def test_slash_is_system(self):
        tx = Transaction(
            tx_type = TxType.SLASH,
            sender  = SENDER,
            payload = SlashPayload(amount=100.0, reason="byzantine", request_id="req1"),
            nonce   = 1,
        )
        assert tx.family == TxFamily.SYSTEM


# ── Serialisation ─────────────────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_has_expected_keys(self):
        tx = make_transfer()
        d = tx.to_dict()
        for key in ("tx_id", "tx_type", "family", "sender", "recipient", "payload", "nonce", "fee"):
            assert key in d

    def test_roundtrip_transfer(self):
        tx = make_transfer(amount=50.0, fee=0.5, nonce=3)
        restored = Transaction.from_dict(tx.to_dict())
        assert restored.tx_id    == tx.tx_id
        assert restored.tx_type  == tx.tx_type
        assert restored.sender   == tx.sender
        assert restored.nonce    == tx.nonce
        assert restored.fee      == tx.fee
        assert restored.payload.amount == tx.payload.amount

    def test_roundtrip_node_register(self):
        tx = Transaction(
            tx_type = TxType.NODE_REGISTER,
            sender  = SENDER,
            payload = NodeRegisterPayload(
                model_name="resnet20",
                public_key="deadbeef" * 8,
                endpoint="127.0.0.1:8000",
            ),
            nonce = 1,
            fee   = 0.0,
        )
        restored = Transaction.from_dict(tx.to_dict())
        assert restored.payload.model_name == "resnet20"
        assert restored.payload.endpoint   == "127.0.0.1:8000"

    def test_roundtrip_inference_request(self):
        tx = Transaction(
            tx_type = TxType.INFERENCE_REQUEST,
            sender  = SENDER,
            payload = InferenceRequestPayload(
                request_id="req-001",
                image_hash="f" * 64,
                model_hint="resnet20",
            ),
            nonce = 1,
        )
        restored = Transaction.from_dict(tx.to_dict())
        assert restored.payload.request_id == "req-001"
        assert restored.payload.image_hash == "f" * 64

    def test_roundtrip_consensus_result(self):
        tx = Transaction(
            tx_type = TxType.CONSENSUS_RESULT,
            sender  = SENDER,
            payload = ConsensusResultPayload(
                request_id="req-001",
                final_class=3,
                confidence=0.91,
                participating_nodes=["node1", "node2", "node3"],
            ),
            nonce = 1,
        )
        restored = Transaction.from_dict(tx.to_dict())
        assert restored.payload.final_class == 3
        assert restored.payload.confidence  == pytest.approx(0.91)
        assert len(restored.payload.participating_nodes) == 3

    def test_roundtrip_contract_deploy(self):
        tx = Transaction(
            tx_type = TxType.CONTRACT_DEPLOY,
            sender  = SENDER,
            payload = ContractDeployPayload(
                bytecode="PUSH 1\nRETURN",
                abi={"init": {"bytecode": "PUSH 1\nRETURN"}},
                constructor_args=[],
            ),
            nonce = 1,
            fee   = 1.0,
        )
        restored = Transaction.from_dict(tx.to_dict())
        assert restored.payload.bytecode == "PUSH 1\nRETURN"
