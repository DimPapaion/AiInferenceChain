"""
Unit tests for core/blockchain/block.py
"""

import pytest
from core.blockchain import (
    Block, BlockHeader, BlockType, ConsensusProof,
    Transaction, TxType,
    TokenTransferPayload, InferenceRequestPayload,
    compute_merkle_root, now,
)

SENDER    = "a" * 40
RECIPIENT = "b" * 40
PROPOSER  = "c" * 40
PREV_HASH = "0" * 64


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_transfer(nonce=1):
    return Transaction(
        tx_type   = TxType.TOKEN_TRANSFER,
        sender    = SENDER,
        recipient = RECIPIENT,
        payload   = TokenTransferPayload(amount=5.0),
        nonce     = nonce,
        fee       = 0.1,
    )

def make_inference_tx():
    return Transaction(
        tx_type = TxType.INFERENCE_REQUEST,
        sender  = SENDER,
        payload = InferenceRequestPayload(
            request_id="req-001",
            image_hash="f" * 64,
            model_hint="resnet20",
        ),
        nonce = 1,
    )

def make_pos_block(simple_txs=None):
    simple_txs = simple_txs or []
    merkle = compute_merkle_root(simple_txs)
    header = BlockHeader(
        prev_hash   = PREV_HASH,
        height      = 1,
        timestamp   = now(),
        proposer_id = PROPOSER,
        merkle_root = merkle,
        block_type  = BlockType.POS,
        view        = 0,
    )
    proof = ConsensusProof(consensus_type=BlockType.POS, view=0,
                           signatures=[(PROPOSER, "sig1"), ("d"*40, "sig2"), ("e"*40, "sig3")])
    return Block(header=header, simple_txs=simple_txs, consensus_proof=proof)

def make_qoi_block():
    inf_tx     = make_inference_tx()
    simple_txs = [make_transfer(nonce=1)]
    all_txs    = [inf_tx] + simple_txs
    merkle     = compute_merkle_root(all_txs)
    header     = BlockHeader(
        prev_hash   = PREV_HASH,
        height      = 1,
        timestamp   = now(),
        proposer_id = PROPOSER,
        merkle_root = merkle,
        block_type  = BlockType.QOI,
        view        = 0,
    )
    proof = ConsensusProof(consensus_type=BlockType.QOI, view=0,
                           signatures=[(PROPOSER, "sig1"), ("d"*40, "sig2"), ("e"*40, "sig3")])
    return Block(header=header, simple_txs=simple_txs,
                 consensus_proof=proof, inference_tx=inf_tx)


# ── BlockHeader ───────────────────────────────────────────────────────────────

class TestBlockHeader:
    def test_hash_is_64_hex(self):
        h = BlockHeader(
            prev_hash=PREV_HASH, height=1, timestamp=1.0,
            proposer_id=PROPOSER, merkle_root="0"*64,
            block_type=BlockType.POS, view=0,
        )
        assert len(h.block_hash) == 64

    def test_different_heights_different_hashes(self):
        h1 = BlockHeader(prev_hash=PREV_HASH, height=1, timestamp=1.0,
                         proposer_id=PROPOSER, merkle_root="0"*64,
                         block_type=BlockType.POS, view=0)
        h2 = BlockHeader(prev_hash=PREV_HASH, height=2, timestamp=1.0,
                         proposer_id=PROPOSER, merkle_root="0"*64,
                         block_type=BlockType.POS, view=0)
        assert h1.block_hash != h2.block_hash

    def test_roundtrip(self):
        h = BlockHeader(prev_hash=PREV_HASH, height=1, timestamp=1.0,
                        proposer_id=PROPOSER, merkle_root="0"*64,
                        block_type=BlockType.QOI, view=2)
        restored = BlockHeader.from_dict(h.to_dict())
        assert restored.block_hash  == h.block_hash
        assert restored.block_type  == BlockType.QOI
        assert restored.view        == 2


# ── ConsensusProof ────────────────────────────────────────────────────────────

class TestConsensusProof:
    def test_is_valid_with_enough_sigs(self):
        proof = ConsensusProof(BlockType.POS, view=0)
        proof.add_signature("node1", "sig1")
        proof.add_signature("node2", "sig2")
        proof.add_signature("node3", "sig3")
        assert proof.is_valid(f=1)   # 2*1+1 = 3

    def test_not_valid_with_too_few(self):
        proof = ConsensusProof(BlockType.POS, view=0)
        proof.add_signature("node1", "sig1")
        proof.add_signature("node2", "sig2")
        assert not proof.is_valid(f=1)  # needs 3

    def test_no_duplicate_signatures(self):
        proof = ConsensusProof(BlockType.POS, view=0)
        proof.add_signature("node1", "sig1")
        proof.add_signature("node1", "sig1_again")
        assert len(proof.signatures) == 1

    def test_roundtrip(self):
        proof = ConsensusProof(BlockType.QOI, view=3,
                               signatures=[("n1", "s1"), ("n2", "s2")])
        restored = ConsensusProof.from_dict(proof.to_dict())
        assert restored.view == 3
        assert restored.consensus_type == BlockType.QOI
        assert len(restored.signatures) == 2


# ── Block construction ────────────────────────────────────────────────────────

class TestBlock:
    def test_pos_block_no_inference_tx(self):
        block = make_pos_block([make_transfer()])
        assert block.header.block_type == BlockType.POS
        assert block.inference_tx is None

    def test_qoi_block_has_inference_tx(self):
        block = make_qoi_block()
        assert block.header.block_type == BlockType.QOI
        assert block.inference_tx is not None

    def test_qoi_block_without_inference_tx_raises(self):
        merkle = compute_merkle_root([])
        header = BlockHeader(prev_hash=PREV_HASH, height=1, timestamp=now(),
                             proposer_id=PROPOSER, merkle_root=merkle,
                             block_type=BlockType.QOI, view=0)
        proof = ConsensusProof(BlockType.QOI, view=0)
        with pytest.raises(ValueError, match="must contain an inference_tx"):
            Block(header=header, simple_txs=[], consensus_proof=proof, inference_tx=None)

    def test_pos_block_with_inference_tx_raises(self):
        inf_tx = make_inference_tx()
        merkle = compute_merkle_root([inf_tx])
        header = BlockHeader(prev_hash=PREV_HASH, height=1, timestamp=now(),
                             proposer_id=PROPOSER, merkle_root=merkle,
                             block_type=BlockType.POS, view=0)
        proof = ConsensusProof(BlockType.POS, view=0)
        with pytest.raises(ValueError, match="cannot contain an inference_tx"):
            Block(header=header, simple_txs=[], consensus_proof=proof, inference_tx=inf_tx)

    def test_merkle_root_verification(self):
        block = make_qoi_block()
        assert block.verify_merkle_root()

    def test_all_transactions_order(self):
        block = make_qoi_block()
        txs = block.all_transactions
        assert txs[0].tx_type == TxType.INFERENCE_REQUEST
        assert txs[1].tx_type == TxType.TOKEN_TRANSFER

    def test_roundtrip_pos_block(self):
        block = make_pos_block([make_transfer()])
        restored = Block.from_dict(block.to_dict())
        assert restored.hash == block.hash
        assert restored.height == block.height
        assert len(restored.simple_txs) == 1

    def test_roundtrip_qoi_block(self):
        block = make_qoi_block()
        restored = Block.from_dict(block.to_dict())
        assert restored.hash == block.hash
        assert restored.inference_tx is not None
        assert restored.inference_tx.tx_id == block.inference_tx.tx_id
