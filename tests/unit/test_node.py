"""
Unit tests for core/node/ — identity, PoM, InferenceNode, PoSNode.
"""

import pytest

from core.node import (
    NodeIdentity, pubkey_to_address, verify_signature, make_test_identity,
    InferenceNode, NodeStatus, ModelHandle,
    PoSNode, PoSNodeStatus,
    generate_challenge_indices, generate_challenge_tx,
    verify_model_response, tally_pom, PoMVerificationState,
)
from core.blockchain.constants import (
    POM_CHALLENGE_SIZE, MIN_MODEL_ACCURACY,
    NODE_TYPE_DNN, NODE_TYPE_POS,
)
from core.blockchain.transaction import TxType


# ═════════════════════════════════════════════════════════════════════════════
# NodeIdentity
# ═════════════════════════════════════════════════════════════════════════════

class TestNodeIdentity:
    def test_generate_produces_unique_identities(self):
        a = NodeIdentity.generate()
        b = NodeIdentity.generate()
        assert a.address != b.address

    def test_address_is_40_hex_chars(self):
        identity = NodeIdentity.generate()
        assert len(identity.address) == 40
        int(identity.address, 16)   # must be valid hex

    def test_from_private_key_roundtrip(self):
        original = NodeIdentity.generate()
        restored = NodeIdentity.from_private_key(original.private_key_hex)
        assert restored.address == original.address
        assert restored.public_key_hex == original.public_key_hex

    def test_sign_and_verify_dict(self):
        identity = NodeIdentity.generate()
        data = {"msg": "hello", "value": 42}
        sig = identity.sign(data)
        assert verify_signature(identity.public_key_hex, data, sig)

    def test_sign_and_verify_string(self):
        identity = NodeIdentity.generate()
        sig = identity.sign("tx_id_abc")
        assert verify_signature(identity.public_key_hex, "tx_id_abc", sig)

    def test_wrong_key_fails_verification(self):
        a = NodeIdentity.generate()
        b = NodeIdentity.generate()
        sig = a.sign("data")
        assert not verify_signature(b.public_key_hex, "data", sig)

    def test_pubkey_to_address_deterministic(self):
        identity = NodeIdentity.generate()
        assert pubkey_to_address(identity.public_key_hex) == identity.address

    def test_make_test_identity_deterministic(self):
        id1 = make_test_identity(7)
        id2 = make_test_identity(7)
        assert id1.address == id2.address

    def test_make_test_identity_different_seeds(self):
        id1 = make_test_identity(1)
        id2 = make_test_identity(2)
        assert id1.address != id2.address

    def test_to_dict_no_private_key_by_default(self):
        identity = NodeIdentity.generate()
        d = identity.to_dict()
        assert "private_key" not in d
        assert "public_key" in d
        assert "address" in d

    def test_to_dict_with_private_key(self):
        identity = NodeIdentity.generate()
        d = identity.to_dict(include_private=True)
        assert "private_key" in d


# ═════════════════════════════════════════════════════════════════════════════
# PoM — challenge generation and verification
# ═════════════════════════════════════════════════════════════════════════════

class TestPoM:
    PREV_HASH = "a" * 64
    NODE_ADDR = "b" * 40

    def test_challenge_indices_correct_size(self):
        indices = generate_challenge_indices(self.PREV_HASH, self.NODE_ADDR)
        assert len(indices) == POM_CHALLENGE_SIZE

    def test_challenge_indices_are_unique(self):
        indices = generate_challenge_indices(self.PREV_HASH, self.NODE_ADDR)
        assert len(indices) == len(set(indices))

    def test_challenge_indices_in_range(self):
        indices = generate_challenge_indices(self.PREV_HASH, self.NODE_ADDR, dataset_size=10_000)
        assert all(0 <= i < 10_000 for i in indices)

    def test_challenge_deterministic(self):
        i1 = generate_challenge_indices(self.PREV_HASH, self.NODE_ADDR)
        i2 = generate_challenge_indices(self.PREV_HASH, self.NODE_ADDR)
        assert i1 == i2

    def test_different_inputs_different_indices(self):
        i1 = generate_challenge_indices(self.PREV_HASH, "a" * 40)
        i2 = generate_challenge_indices(self.PREV_HASH, "b" * 40)
        assert i1 != i2

    def test_generate_challenge_tx_structure(self):
        tx = generate_challenge_tx(self.NODE_ADDR, self.PREV_HASH)
        assert tx.tx_type == TxType.MODEL_CHALLENGE
        assert len(tx.payload.challenge_indices) == POM_CHALLENGE_SIZE
        assert len(tx.payload.ground_truth) == POM_CHALLENGE_SIZE

    def test_pom_verification_state_admitted(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        for i in range(3):   # f=1 → 2f+1 = 3
            state.add_verify(str(i), verified=True, accuracy=0.85)
        assert state.is_admitted(f=1)

    def test_pom_verification_state_rejected(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        for i in range(3):
            state.add_verify(str(i), verified=False, accuracy=0.5)
        assert state.is_rejected(f=1, total_validators=4)

    def test_pom_no_duplicate_verifiers(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        state.add_verify("v1", verified=True, accuracy=0.9)
        state.add_verify("v1", verified=True, accuracy=0.9)   # duplicate
        assert len(state.positive) == 1

    def test_tally_pom_admitted(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        for i in range(3):
            state.add_verify(str(i), verified=True, accuracy=0.85)
        tx = tally_pom(state, f=1, total_validators=4)
        assert tx is not None
        assert tx.tx_type == TxType.NODE_ADMITTED

    def test_tally_pom_rejected(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        for i in range(3):
            state.add_verify(str(i), verified=False, accuracy=0.4)
        tx = tally_pom(state, f=1, total_validators=4)
        assert tx is not None
        assert tx.tx_type == TxType.NODE_REJECTED

    def test_tally_pom_still_collecting(self):
        state = PoMVerificationState(
            node_id="n1", node_type=NODE_TYPE_DNN,
            weights_hash="wh",
        )
        state.add_verify("v1", verified=True, accuracy=0.85)   # only 1 of 3
        tx = tally_pom(state, f=1, total_validators=4)
        assert tx is None


# ═════════════════════════════════════════════════════════════════════════════
# PoSNode
# ═════════════════════════════════════════════════════════════════════════════

class TestPoSNode:
    def _make_node(self) -> PoSNode:
        return PoSNode(
            identity=make_test_identity(10),
            endpoint="127.0.0.1:9000",
            f=1,
        )

    def test_initial_status_unregistered(self):
        node = self._make_node()
        assert node.status == PoSNodeStatus.UNREGISTERED

    def test_build_register_tx(self):
        node = self._make_node()
        tx   = node.build_register_tx()
        assert tx.tx_type == TxType.NODE_REGISTER_POS
        assert tx.sender  == node.address
        assert tx.signature != ""
        assert node.status == PoSNodeStatus.PENDING

    def test_build_stake_tx(self):
        node = self._make_node()
        tx   = node.build_stake_tx(amount=5000.0)
        assert tx.tx_type == TxType.STAKE
        assert tx.payload.amount == 5000.0

    def test_nonce_increments(self):
        node = self._make_node()
        tx1  = node.build_register_tx()
        tx2  = node.build_stake_tx(1000.0)
        assert tx2.nonce == tx1.nonce + 1

    def test_is_proposer(self):
        node = self._make_node()
        node.start_pos_round(proposer_id=node.address)
        assert node.is_proposer()

    def test_is_not_proposer(self):
        node = self._make_node()
        node.start_pos_round(proposer_id="other" * 8)
        assert not node.is_proposer()

    def test_sync_nonce(self):
        node = self._make_node()
        node.sync_nonce(42)
        tx = node.build_stake_tx(100.0)
        assert tx.nonce == 43


# ═════════════════════════════════════════════════════════════════════════════
# InferenceNode (no model loaded — tx-building only)
# ═════════════════════════════════════════════════════════════════════════════

class TestInferenceNodeTxs:
    def _make_node(self) -> InferenceNode:
        handle = ModelHandle(
            name="resnet20",
            architecture={"layers": 20},
            weights_path="weights/resnet20.pt",
            weights_hash="ab" * 32,
            dataset_id="cifar10",
        )
        return InferenceNode(
            identity=make_test_identity(5),
            model=handle,
            endpoint="127.0.0.1:8001",
            f=1,
        )

    def test_initial_status_unregistered(self):
        node = self._make_node()
        assert node.status == NodeStatus.UNREGISTERED

    def test_build_register_tx(self):
        node = self._make_node()
        tx   = node.build_register_tx()
        assert tx.tx_type == TxType.NODE_REGISTER_DNN
        assert tx.sender  == node.address
        assert tx.signature != ""
        assert node.status == NodeStatus.PENDING_POM

    def test_build_stake_tx(self):
        node = self._make_node()
        tx   = node.build_stake_tx(amount=10_000.0)
        assert tx.tx_type == TxType.STAKE
        assert tx.payload.amount == 10_000.0

    def test_nonce_increments(self):
        node = self._make_node()
        tx1  = node.build_register_tx()
        tx2  = node.build_stake_tx(1000.0)
        assert tx2.nonce == tx1.nonce + 1

    def test_address_is_40_chars(self):
        node = self._make_node()
        assert len(node.address) == 40

    def test_node_id_equals_address(self):
        node = self._make_node()
        assert node.node_id == node.address

    def test_sync_nonce(self):
        node = self._make_node()
        node.sync_nonce(99)
        tx = node.build_stake_tx(100.0)
        assert tx.nonce == 100

    def test_repr_contains_address_prefix(self):
        node = self._make_node()
        assert node.address[:8] in repr(node)
