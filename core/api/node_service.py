"""
NodeService — the single shared state object for a running InferenceChain node.

Every API route (REST and future P2P) reads/writes through this object.
It owns:
  - Chain          — the committed ledger
  - Mempool        — pending transactions
  - known_peers    — set of peer endpoints for gossip (populated by P2P layer later)

Thread/async safety: all mutations are protected by asyncio.Lock.
The consensus engine (block production loop) will be wired in when the P2P
layer is added; for now callers can trigger manual block sealing via seal_block().
"""

from __future__ import annotations

import asyncio
from typing import Optional

from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.chain import Chain
from core.blockchain.constants import DEFAULT_F, MAX_SIMPLE_TXS
from core.blockchain.genesis import create_genesis_block
from core.blockchain.mempool import Mempool
from core.blockchain.transaction import Transaction, TxType
from core.blockchain.utils import compute_merkle_root, now


class NodeService:
    """
    Singleton service wiring Chain + Mempool together.
    One instance per running node process.
    """

    def __init__(self, chain: Chain, mempool: Optional[Mempool] = None) -> None:
        self.chain    = chain
        self.mempool  = mempool or Mempool()
        self._lock    = asyncio.Lock()
        self.peers: set[str] = set()   # peer base URLs, e.g. "http://1.2.3.4:8000"

    # ── Transaction submission ─────────────────────────────────────────────────

    async def submit_tx(self, tx: Transaction) -> dict:
        """
        Accept a transaction into the mempool.
        Returns {"accepted": bool, "tx_id": str, "reason": str|None}
        """
        async with self._lock:
            # Basic nonce validation against current chain state
            expected_nonce = self.chain.state.nonce_of(tx.sender) + 1
            if tx.nonce != expected_nonce:
                return {
                    "accepted": False,
                    "tx_id":    tx.tx_id,
                    "reason":   f"invalid nonce: expected {expected_nonce}, got {tx.nonce}",
                }
            accepted = self.mempool.add(tx)
            return {
                "accepted": accepted,
                "tx_id":    tx.tx_id,
                "reason":   None if accepted else "mempool full or duplicate",
            }

    def get_tx(self, tx_id: str) -> Optional[dict]:
        """
        Look up a transaction: mempool (pending) or chain (confirmed).
        Returns serialised tx dict with a 'status' field, or None.
        """
        # 1. Check mempool first
        pending = self.mempool.get_tx(tx_id)
        if pending:
            d = pending.to_dict()
            d["status"] = "pending"
            return d

        # 2. Scan chain blocks (most-recent-first)
        for block in reversed(self.chain.blocks):
            for tx in block.all_transactions:
                if tx.tx_id == tx_id:
                    d = tx.to_dict()
                    d["status"]        = "confirmed"
                    d["block_height"]  = block.height
                    d["block_hash"]    = block.hash
                    return d
        return None

    # ── Chain queries ──────────────────────────────────────────────────────────

    def get_block(self, height: int) -> Optional[Block]:
        return self.chain.get_block(height)

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        return self.chain.get_block_by_hash(block_hash)

    # ── State queries ──────────────────────────────────────────────────────────

    def balance_of(self, address: str) -> float:
        return self.chain.state.balance_of(address)

    def stake_of(self, address: str) -> float:
        return self.chain.state.stake_of(address)

    def nonce_of(self, address: str) -> int:
        return self.chain.state.nonce_of(address)

    def reputation_of(self, address: str) -> float:
        return self.chain.state.reputation_of(address)

    def get_node_info(self, node_id: str) -> Optional[dict]:
        node = self.chain.state.nodes.get(node_id)
        return node.to_dict() if node else None

    def active_nodes(self) -> list[dict]:
        return [n.to_dict() for n in self.chain.state.active_nodes()]

    def dnn_validators(self) -> list[dict]:
        return [n.to_dict() for n in self.chain.state.dnn_validators()]

    def pos_validators(self) -> list[dict]:
        return [n.to_dict() for n in self.chain.state.pos_validators()]

    # ── Inference queries ──────────────────────────────────────────────────────

    def get_inference_result(self, request_id: str) -> Optional[dict]:
        return self.chain.get_inference_result(request_id)

    # ── Block sealing (dev / single-node mode) ─────────────────────────────────

    async def seal_block(self, proposer_id: str) -> Optional[Block]:
        """
        Manually seal a PoS block from mempool contents.
        Used in dev/single-node mode and by the consensus engine.
        In real multi-node mode, the consensus engine calls this after 2f+1 votes.
        """
        async with self._lock:
            account_nonces = {
                addr: self.chain.state.nonce_of(addr)
                for addr in self.chain.state.nonces
            }
            simple_txs = self.mempool.select_simple(account_nonces, MAX_SIMPLE_TXS)

            merkle_root = compute_merkle_root(simple_txs)
            header = BlockHeader(
                prev_hash   = self.chain.tip.hash,
                height      = self.chain.height + 1,
                timestamp   = now(),
                proposer_id = proposer_id,
                merkle_root = merkle_root,
                block_type  = BlockType.POS,
                view        = 0,
            )
            # In dev mode we use a single-signer proof (f=0 effectively)
            proof = ConsensusProof(
                consensus_type = BlockType.POS,
                view           = 0,
                signatures     = [
                    (proposer_id, "dev"),
                    (proposer_id, "dev"),
                    (proposer_id, "dev"),
                ],
            )
            block = Block(
                header          = header,
                simple_txs      = simple_txs,
                consensus_proof = proof,
            )
            try:
                self.chain.append(block)
                # Clean up mempool
                committed_ids = [tx.tx_id for tx in simple_txs]
                self.mempool.remove(committed_ids)
                return block
            except ValueError:
                return None

    # ── P2P block ingestion ───────────────────────────────────────────────────

    async def ingest_block(self, block: Block) -> dict:
        """
        Accept a block broadcast by a peer.
        Returns {"accepted": bool, "reason": str|None}
        """
        async with self._lock:
            try:
                self.chain.append(block)
                # Remove committed txs from mempool
                committed_ids = [tx.tx_id for tx in block.all_transactions]
                self.mempool.remove(committed_ids)
                return {"accepted": True, "reason": None}
            except ValueError as e:
                return {"accepted": False, "reason": str(e)}

    # ── Peer management ────────────────────────────────────────────────────────

    def add_peer(self, base_url: str) -> None:
        self.peers.add(base_url.rstrip("/"))

    def remove_peer(self, base_url: str) -> None:
        self.peers.discard(base_url.rstrip("/"))


# ── Factory ───────────────────────────────────────────────────────────────────

def create_node_service(
    initial_allocations: dict[str, float] | None = None,
    initial_nodes: list[dict] | None = None,
    f: int = DEFAULT_F,
) -> NodeService:
    """
    Bootstrap a fresh NodeService with a genesis block.
    """
    genesis = create_genesis_block(
        initial_allocations=initial_allocations,
        initial_nodes=initial_nodes,
    )
    chain = Chain(genesis, f=f)
    return NodeService(chain=chain)
