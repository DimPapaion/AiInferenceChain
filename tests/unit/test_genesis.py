"""
Unit tests for core/blockchain/genesis.py
"""

import pytest
from core.blockchain import (
    Chain, Block, BlockType,
    TxType,
    create_genesis_block, default_genesis, GENESIS_ADDRESS,
    GENESIS_ALLOCATION,
)

ALICE = "a" * 40
BOB   = "b" * 40


class TestCreateGenesisBlock:
    def test_genesis_height_zero(self):
        g = create_genesis_block()
        assert g.height == 0

    def test_genesis_prev_hash_all_zeros(self):
        g = create_genesis_block()
        assert g.header.prev_hash == "0" * 64

    def test_genesis_block_type_is_pos(self):
        g = create_genesis_block()
        assert g.header.block_type == BlockType.POS

    def test_genesis_has_allocation_txs(self):
        g = create_genesis_block(initial_allocations={ALICE: 1000.0, BOB: 500.0})
        tx_types = [tx.tx_type for tx in g.simple_txs]
        assert tx_types.count(TxType.TOKEN_TRANSFER) == 2

    def test_genesis_has_node_register_txs(self):
        nodes = [{"address": ALICE, "model_name": "resnet20",
                  "public_key": "aa" * 32, "endpoint": "127.0.0.1:8000"}]
        g = create_genesis_block(initial_nodes=nodes)
        tx_types = [tx.tx_type for tx in g.simple_txs]
        assert TxType.NODE_REGISTER in tx_types

    def test_genesis_merkle_root_valid(self):
        g = create_genesis_block(initial_allocations={ALICE: 100.0})
        assert g.verify_merkle_root()

    def test_genesis_no_inference_tx(self):
        g = create_genesis_block()
        assert g.inference_tx is None


class TestDefaultGenesis:
    def test_default_genesis_is_block(self):
        g = default_genesis()
        assert isinstance(g, Block)

    def test_default_genesis_has_protocol_allocation(self):
        chain = Chain(default_genesis())
        assert chain.state.balance_of("a" * 40) == pytest.approx(GENESIS_ALLOCATION)


class TestChainFromGenesis:
    def test_chain_initialises_from_custom_genesis(self):
        genesis = create_genesis_block(
            initial_allocations={ALICE: 50_000.0, BOB: 25_000.0},
        )
        chain = Chain(genesis)
        assert chain.height == 0
        assert chain.state.balance_of(ALICE) == pytest.approx(50_000.0)
        assert chain.state.balance_of(BOB)   == pytest.approx(25_000.0)

    def test_chain_with_nodes_at_genesis(self):
        nodes = [
            {"address": ALICE, "model_name": "resnet20",
             "public_key": "aa" * 32, "endpoint": "127.0.0.1:8000"},
            {"address": BOB,   "model_name": "vgg11_bn",
             "public_key": "bb" * 32, "endpoint": "127.0.0.1:8001"},
        ]
        genesis = create_genesis_block(initial_nodes=nodes)
        chain   = Chain(genesis)
        assert ALICE in chain.state.nodes
        assert BOB   in chain.state.nodes
        assert chain.state.nodes[ALICE].model_name == "resnet20"
        assert chain.state.nodes[BOB].model_name   == "vgg11_bn"
