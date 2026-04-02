"""
Unit tests for core/blockchain/chain.py
"""

import pytest
from core.blockchain import (
    Chain, Block, BlockHeader, BlockType, ConsensusProof,
    Transaction, TxType,
    TokenTransferPayload, StakePayload, UnstakePayload,
    NodeRegisterPayload, RewardPayload, SlashPayload,
    InferenceRequestPayload, ConsensusResultPayload,
    create_genesis_block, default_genesis,
    compute_merkle_root, now,
    MIN_STAKE,
)

ALICE   = "a" * 40
BOB     = "b" * 40
CHARLIE = "c" * 40


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chain(allocations=None):
    allocations = allocations or {ALICE: 100_000.0, BOB: 50_000.0}
    genesis = create_genesis_block(initial_allocations=allocations)
    return Chain(genesis, f=1)


def build_pos_block(chain, simple_txs, extra_system_txs=None):
    """Build a valid POS block on top of the chain tip."""
    all_txs = list(simple_txs) + (extra_system_txs or [])
    merkle  = compute_merkle_root(all_txs)
    header  = BlockHeader(
        prev_hash   = chain.tip.hash,
        height      = chain.height + 1,
        timestamp   = now(),
        proposer_id = CHARLIE,
        merkle_root = merkle,
        block_type  = BlockType.POS,
        view        = 0,
    )
    proof = ConsensusProof(BlockType.POS, view=0, signatures=[
        (ALICE, "s1"), (BOB, "s2"), (CHARLIE, "s3")
    ])
    return Block(header=header, simple_txs=simple_txs,
                 consensus_proof=proof, system_txs=extra_system_txs or [])


def make_transfer_tx(sender, recipient, amount, nonce, fee=0.1):
    return Transaction(
        tx_type   = TxType.TOKEN_TRANSFER,
        sender    = sender,
        recipient = recipient,
        payload   = TokenTransferPayload(amount=amount),
        nonce     = nonce,
        fee       = fee,
    )

def make_stake_tx(sender, amount, nonce, fee=0.1):
    return Transaction(
        tx_type = TxType.STAKE,
        sender  = sender,
        payload = StakePayload(amount=amount),
        nonce   = nonce,
        fee     = fee,
    )

def make_reward_tx(recipient, amount, request_id="req-001"):
    return Transaction(
        tx_type   = TxType.REWARD,
        sender    = "0" * 40,
        recipient = recipient,
        payload   = RewardPayload(amount=amount, reason="honest", request_id=request_id),
        nonce     = 1,
    )

def make_slash_tx(sender, amount, request_id="req-001"):
    return Transaction(
        tx_type = TxType.SLASH,
        sender  = sender,
        payload = SlashPayload(amount=amount, reason="byzantine", request_id=request_id),
        nonce   = 1,
    )


# ── Genesis ───────────────────────────────────────────────────────────────────

class TestGenesis:
    def test_chain_starts_at_height_zero(self):
        chain = make_chain()
        assert chain.height == 0

    def test_genesis_allocations(self):
        chain = make_chain()
        assert chain.state.balance_of(ALICE) == pytest.approx(100_000.0)
        assert chain.state.balance_of(BOB)   == pytest.approx(50_000.0)

    def test_unknown_address_has_zero_balance(self):
        chain = make_chain()
        assert chain.state.balance_of("f" * 40) == 0.0


# ── Append blocks ─────────────────────────────────────────────────────────────

class TestAppend:
    def test_append_valid_pos_block(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=1)
        block = build_pos_block(chain, [tx])
        chain.append(block)
        assert chain.height == 1

    def test_wrong_prev_hash_rejected(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=1)
        merkle = compute_merkle_root([tx])
        header = BlockHeader(
            prev_hash   = "bad" + "0" * 61,
            height      = 1,
            timestamp   = now(),
            proposer_id = CHARLIE,
            merkle_root = merkle,
            block_type  = BlockType.POS,
            view        = 0,
        )
        proof = ConsensusProof(BlockType.POS, view=0,
                               signatures=[(ALICE,"s1"),(BOB,"s2"),(CHARLIE,"s3")])
        block = Block(header=header, simple_txs=[tx], consensus_proof=proof)
        with pytest.raises(ValueError, match="Invalid prev_hash"):
            chain.append(block)

    def test_wrong_height_rejected(self):
        chain = make_chain()
        tx = make_transfer_tx(ALICE, BOB, 100.0, nonce=1)
        merkle = compute_merkle_root([tx])
        header = BlockHeader(
            prev_hash   = chain.tip.hash,
            height      = 5,          # wrong
            timestamp   = now(),
            proposer_id = CHARLIE,
            merkle_root = merkle,
            block_type  = BlockType.POS,
            view        = 0,
        )
        proof = ConsensusProof(BlockType.POS, view=0,
                               signatures=[(ALICE,"s1"),(BOB,"s2"),(CHARLIE,"s3")])
        block = Block(header=header, simple_txs=[tx], consensus_proof=proof)
        with pytest.raises(ValueError, match="Invalid height"):
            chain.append(block)

    def test_insufficient_signatures_rejected(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=1)
        merkle = compute_merkle_root([tx])
        header = BlockHeader(
            prev_hash=chain.tip.hash, height=1, timestamp=now(),
            proposer_id=CHARLIE, merkle_root=merkle,
            block_type=BlockType.POS, view=0,
        )
        proof = ConsensusProof(BlockType.POS, view=0,
                               signatures=[(ALICE, "s1")])  # only 1, need 3
        block = Block(header=header, simple_txs=[tx], consensus_proof=proof)
        with pytest.raises(ValueError, match="Insufficient consensus"):
            chain.append(block)


# ── State transitions ─────────────────────────────────────────────────────────

class TestStateTransitions:
    def test_token_transfer_updates_balances(self):
        chain  = make_chain()
        before = chain.state.balance_of(BOB)
        tx     = make_transfer_tx(ALICE, BOB, 1000.0, nonce=1, fee=0.0)
        chain.append(build_pos_block(chain, [tx]))
        assert chain.state.balance_of(BOB) == pytest.approx(before + 1000.0)
        assert chain.state.balance_of(ALICE) == pytest.approx(100_000.0 - 1000.0)

    def test_fee_goes_to_proposer(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=1, fee=5.0)
        chain.append(build_pos_block(chain, [tx]))
        assert chain.state.balance_of(CHARLIE) == pytest.approx(5.0)

    def test_nonce_increments(self):
        chain = make_chain()
        assert chain.state.nonce_of(ALICE) == 0
        tx = make_transfer_tx(ALICE, BOB, 100.0, nonce=1, fee=0.0)
        chain.append(build_pos_block(chain, [tx]))
        assert chain.state.nonce_of(ALICE) == 1

    def test_wrong_nonce_rejected(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=99, fee=0.0)
        with pytest.raises(ValueError, match="Invalid nonce"):
            chain.append(build_pos_block(chain, [tx]))

    def test_insufficient_balance_rejected(self):
        chain = make_chain({ALICE: 10.0})
        tx    = make_transfer_tx(ALICE, BOB, 1_000_000.0, nonce=1, fee=0.0)
        with pytest.raises(ValueError, match="Insufficient balance"):
            chain.append(build_pos_block(chain, [tx]))

    def test_stake_moves_tokens(self):
        chain = make_chain()
        tx    = make_stake_tx(ALICE, 5_000.0, nonce=1, fee=0.0)
        chain.append(build_pos_block(chain, [tx]))
        assert chain.state.stake_of(ALICE)   == pytest.approx(5_000.0)
        assert chain.state.balance_of(ALICE) == pytest.approx(95_000.0)

    def test_reward_increases_balance(self):
        chain  = make_chain()
        before = chain.state.balance_of(ALICE)
        reward = make_reward_tx(ALICE, 10.0)
        chain.append(build_pos_block(chain, [], extra_system_txs=[reward]))
        assert chain.state.balance_of(ALICE) == pytest.approx(before + 10.0)

    def test_slash_reduces_stake(self):
        chain    = make_chain()
        stake_tx = make_stake_tx(ALICE, MIN_STAKE * 2, nonce=1, fee=0.0)
        chain.append(build_pos_block(chain, [stake_tx]))
        slash    = make_slash_tx(ALICE, MIN_STAKE)
        chain.append(build_pos_block(chain, [], extra_system_txs=[slash]))
        assert chain.state.stake_of(ALICE) == pytest.approx(MIN_STAKE)

    def test_slash_below_min_deactivates_node(self):
        chain    = make_chain()
        # Register and stake
        reg_tx   = Transaction(
            tx_type = TxType.NODE_REGISTER, sender=ALICE,
            payload = NodeRegisterPayload("resnet20", "aa"*32, "127.0.0.1:8000"),
            nonce=1, fee=0.0,
        )
        stake_tx = make_stake_tx(ALICE, MIN_STAKE, nonce=2, fee=0.0)
        chain.append(build_pos_block(chain, [reg_tx, stake_tx]))
        assert chain.state.nodes[ALICE].is_active

        # Slash all stake
        slash = make_slash_tx(ALICE, MIN_STAKE + 1)
        chain.append(build_pos_block(chain, [], extra_system_txs=[slash]))
        assert not chain.state.nodes[ALICE].is_active


# ── Lookups ───────────────────────────────────────────────────────────────────

class TestLookups:
    def test_get_block_by_height(self):
        chain = make_chain()
        tx    = make_transfer_tx(ALICE, BOB, 100.0, nonce=1, fee=0.0)
        chain.append(build_pos_block(chain, [tx]))
        b = chain.get_block(1)
        assert b is not None
        assert b.height == 1

    def test_get_block_out_of_range(self):
        chain = make_chain()
        assert chain.get_block(999) is None

    def test_get_block_by_hash(self):
        chain = make_chain()
        tip   = chain.tip
        found = chain.get_block_by_hash(tip.hash)
        assert found is not None
        assert found.hash == tip.hash
