"""
Unit tests for core/storage/db.py (ChainDB + open_or_create_chain).
"""

import tempfile
from pathlib import Path

import pytest

from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.chain import Chain
from core.blockchain.genesis import create_genesis_block
from core.blockchain.utils import compute_merkle_root, now
from core.storage.db import ChainDB, open_or_create_chain


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chain() -> Chain:
    genesis = create_genesis_block(initial_allocations={"alice": 1000.0})
    return Chain(genesis, f=0)


def _append_pos_block(chain: Chain, height: int) -> Block:
    header = BlockHeader(
        prev_hash   = chain.tip.hash,
        height      = height,
        timestamp   = now(),
        proposer_id = "alice",
        merkle_root = compute_merkle_root([]),   # correct empty-tx merkle root
        block_type  = BlockType.POS,
        view        = 0,
    )
    proof = ConsensusProof(
        consensus_type = BlockType.POS,
        view           = 0,
        signatures     = [("alice", "sig"), ("alice", "sig"), ("alice", "sig")],
    )
    block = Block(header=header, simple_txs=[], consensus_proof=proof)
    chain.append(block)
    return block


# ── ChainDB round-trip ─────────────────────────────────────────────────────────

class TestChainDB:
    def test_save_and_load_genesis(self, tmp_path):
        chain = _make_chain()
        db    = ChainDB(tmp_path / "chain.db")
        db.save_block(chain.tip)

        loaded = db.load_all_blocks()
        assert len(loaded) == 1
        assert loaded[0].hash == chain.tip.hash

    def test_save_and_load_multiple_blocks(self, tmp_path):
        chain = _make_chain()
        db    = ChainDB(tmp_path / "chain.db")
        db.save_block(chain.tip)                    # genesis

        b1 = _append_pos_block(chain, 1)
        db.save_block(b1)
        b2 = _append_pos_block(chain, 2)
        db.save_block(b2)

        blocks = db.load_all_blocks()
        assert len(blocks) == 3
        assert blocks[-1].hash == b2.hash

    def test_save_and_load_state(self, tmp_path):
        chain = _make_chain()
        db    = ChainDB(tmp_path / "chain.db")
        db.save_state(chain.state)

        state = db.load_state()
        assert state is not None
        assert state.balance_of("alice") == pytest.approx(1000.0)

    def test_idempotent_block_save(self, tmp_path):
        chain = _make_chain()
        db    = ChainDB(tmp_path / "chain.db")
        db.save_block(chain.tip)
        db.save_block(chain.tip)   # second save should not raise

        blocks = db.load_all_blocks()
        assert len(blocks) == 1

    def test_load_empty_db_returns_nothing(self, tmp_path):
        db = ChainDB(tmp_path / "empty.db")
        assert db.load_all_blocks() == []
        assert db.load_state() is None


# ── open_or_create_chain ──────────────────────────────────────────────────────

class TestOpenOrCreateChain:
    def test_creates_chain_when_db_missing(self, tmp_path):
        chain, db = open_or_create_chain(
            db_path             = str(tmp_path / "new.db"),
            initial_allocations = {"bob": 5000.0},
            f                   = 0,
        )
        assert chain.height == 0
        assert chain.state.balance_of("bob") == pytest.approx(5000.0)
        db.close()

    def test_reopens_existing_chain(self, tmp_path):
        db_path = str(tmp_path / "persist.db")
        chain1, db1 = open_or_create_chain(
            db_path             = db_path,
            initial_allocations = {"carol": 9999.0},
            f                   = 0,
        )
        b1 = _append_pos_block(chain1, 1)
        db1.save_block(b1)
        db1.save_state(chain1.state)
        db1.close()

        # Reopen — should replay from DB, not re-create genesis
        chain2, db2 = open_or_create_chain(db_path=db_path, f=0)
        assert chain2.height == 1
        assert chain2.tip.hash == b1.hash
        db2.close()
