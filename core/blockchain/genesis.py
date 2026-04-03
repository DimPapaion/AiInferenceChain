"""
Genesis block factory for InferenceChain.

The genesis block:
  - height = 0, prev_hash = "0" * 64
  - block_type = POS (no inference job yet)
  - Contains initial token allocations as TOKEN_TRANSFER txs
  - Contains initial node registrations as NODE_REGISTER txs
  - Consensus proof is hardcoded (no real consensus at genesis)
"""

from __future__ import annotations

from .block import Block, BlockHeader, BlockType, ConsensusProof
from .transaction import (
    Transaction, TxType,
    TokenTransferPayload, NodeRegisterPayload,
    NodeRegisterDNNPayload, NodeAdmittedPayload, StakePayload,
)
from .utils import compute_merkle_root, now
from .constants import GENESIS_ALLOCATION, MIN_STAKE_DNN

# Sentinel address used as the "protocol" sender for genesis allocations
GENESIS_ADDRESS = "0" * 40


def create_genesis_block(
    initial_allocations: dict[str, float] | None = None,
    initial_nodes: list[dict] | None = None,
    initial_dnn_nodes: list[dict] | None = None,
    proposer_id: str = GENESIS_ADDRESS,
) -> Block:
    """
    Build the genesis block.

    Args:
        initial_allocations: {address: amount} — initial INFER token distribution
        initial_nodes: PoS node dicts with keys:
                       {address, model_name, public_key, endpoint}
        initial_dnn_nodes: DNN node dicts with keys:
                       {address, model_name, public_key, endpoint,
                        weights_hash, dataset_id, architecture, stake}
                       These nodes are registered AND pre-admitted (PoM skipped
                       for dev/testnet).  Each node is also auto-staked with
                       the supplied stake (or MIN_STAKE_DNN if omitted).
        proposer_id: address of the genesis proposer (default: zero address)

    Returns:
        A fully formed genesis Block ready to initialise the Chain.
    """
    simple_txs: list[Transaction] = []
    system_txs: list[Transaction] = []
    ts = now()
    nonce_counter: dict[str, int] = {}

    # ── Token allocations ────────────────────────────────────────────────────
    if initial_allocations:
        for address, amount in initial_allocations.items():
            n = nonce_counter.get(GENESIS_ADDRESS, 0) + 1
            nonce_counter[GENESIS_ADDRESS] = n
            tx = Transaction(
                tx_type   = TxType.TOKEN_TRANSFER,
                sender    = GENESIS_ADDRESS,
                recipient = address,
                payload   = TokenTransferPayload(amount=amount),
                nonce     = n,
                fee       = 0.0,
                timestamp = ts,
                signature = "genesis",
            )
            simple_txs.append(tx)

    # ── PoS node registrations (legacy — auto-admitted) ───────────────────────
    if initial_nodes:
        for node in initial_nodes:
            address = node["address"]
            n = nonce_counter.get(address, 0) + 1
            nonce_counter[address] = n
            tx = Transaction(
                tx_type   = TxType.NODE_REGISTER,
                sender    = address,
                recipient = None,
                payload   = NodeRegisterPayload(
                    model_name = node["model_name"],
                    public_key = node["public_key"],
                    endpoint   = node["endpoint"],
                ),
                nonce     = n,
                fee       = 0.0,
                timestamp = ts,
                signature = "genesis",
            )
            simple_txs.append(tx)

    # ── DNN node registrations (pre-admitted — dev/testnet only) ─────────────
    # Each DNN node gets: NODE_REGISTER_DNN simple tx + STAKE simple tx
    # then NODE_ADMITTED system tx so they start active without PoM ceremony.
    if initial_dnn_nodes:
        sys_nonce = nonce_counter.get(GENESIS_ADDRESS, 0)
        for node in initial_dnn_nodes:
            address     = node["address"]
            stake_amt   = float(node.get("stake", MIN_STAKE_DNN))
            architecture = node.get("architecture", {})

            # Register
            n = nonce_counter.get(address, 0) + 1
            nonce_counter[address] = n
            simple_txs.append(Transaction(
                tx_type   = TxType.NODE_REGISTER_DNN,
                sender    = address,
                payload   = NodeRegisterDNNPayload(
                    model_name   = node["model_name"],
                    architecture = architecture,
                    weights_hash = node.get("weights_hash", ""),
                    endpoint     = node["endpoint"],
                    dataset_id   = node.get("dataset_id", "cifar10"),
                    public_key   = node["public_key"],
                ),
                nonce     = n,
                fee       = 0.0,
                timestamp = ts,
                signature = "genesis",
            ))

            # Auto-stake
            n = nonce_counter.get(address, 0) + 1
            nonce_counter[address] = n
            simple_txs.append(Transaction(
                tx_type   = TxType.STAKE,
                sender    = address,
                payload   = StakePayload(amount=stake_amt),
                nonce     = n,
                fee       = 0.0,
                timestamp = ts,
                signature = "genesis",
            ))

            # Pre-admit (skip PoM) — system tx applied after simple txs
            sys_nonce += 1
            system_txs.append(Transaction(
                tx_type   = TxType.NODE_ADMITTED,
                sender    = GENESIS_ADDRESS,
                payload   = NodeAdmittedPayload(
                    node_id        = address,
                    node_type      = "dnn",
                    final_accuracy = 1.0,   # genesis pre-admission — no PoM
                ),
                nonce     = sys_nonce,
                fee       = 0.0,
                timestamp = ts,
                signature = "genesis",
            ))

    # ── Build block ──────────────────────────────────────────────────────────
    merkle_root = compute_merkle_root(simple_txs)

    header = BlockHeader(
        prev_hash   = "0" * 64,
        height      = 0,
        timestamp   = ts,
        proposer_id = proposer_id,
        merkle_root = merkle_root,
        block_type  = BlockType.POS,
        view        = 0,
    )

    # Genesis consensus proof — hardcoded, no real signatures needed
    proof = ConsensusProof(
        consensus_type = BlockType.POS,
        view           = 0,
        signatures     = [(GENESIS_ADDRESS, "genesis")],
    )

    return Block(
        header          = header,
        simple_txs      = simple_txs,
        consensus_proof = proof,
        inference_tx    = None,
        system_txs      = system_txs,
    )


def default_genesis() -> Block:
    """
    Minimal genesis block with a single protocol allocation.
    Used for testing and local devnet startup.
    """
    return create_genesis_block(
        initial_allocations={
            # Protocol reserve address gets the full genesis allocation
            "a" * 40: GENESIS_ALLOCATION,
        },
        initial_nodes=None,
    )
