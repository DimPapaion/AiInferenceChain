"""
NodeService — the single shared state object for a running InferenceChain node.

Every API route (REST and future P2P) reads/writes through this object.
It owns:
  - Chain          — the committed ledger
  - Mempool        — pending transactions
  - ChainDB        — optional SQLite persistence (None = in-memory only)
  - known_peers    — set of peer endpoints for gossip

Thread/async safety: all mutations are protected by asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from core.blockchain.block import Block, BlockHeader, BlockType, ConsensusProof
from core.blockchain.chain import Chain
from core.blockchain.constants import DEFAULT_F, MAX_SIMPLE_TXS
from core.blockchain.genesis import create_genesis_block
from core.blockchain.mempool import Mempool
from core.blockchain.transaction import Transaction, TxType
from core.blockchain.utils import compute_merkle_root, now

log = logging.getLogger(__name__)


class NodeService:
    """
    Singleton service wiring Chain + Mempool + optional DB together.
    One instance per running node process.
    """

    def __init__(
        self,
        chain:   Chain,
        mempool: Optional[Mempool] = None,
        db=None,        # Optional[ChainDB] — import avoided to keep tests light
    ) -> None:
        self.chain   = chain
        self.mempool = mempool or Mempool()
        self.db      = db       # ChainDB | None
        self._lock   = asyncio.Lock()
        self.peers: set[str] = set()

    # ── Transaction submission ─────────────────────────────────────────────────

    async def submit_tx(self, tx: Transaction) -> dict:
        async with self._lock:
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
        pending = self.mempool.get_tx(tx_id)
        if pending:
            d = pending.to_dict()
            d["status"] = "pending"
            return d
        for block in reversed(self.chain.blocks):
            for tx in block.all_transactions:
                if tx.tx_id == tx_id:
                    d = tx.to_dict()
                    d["status"]       = "confirmed"
                    d["block_height"] = block.height
                    d["block_hash"]   = block.hash
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

    def get_inference_result(self, request_id: str) -> Optional[dict]:
        return self.chain.get_inference_result(request_id)

    # ── Block sealing (dev / single-node mode) ─────────────────────────────────

    async def seal_block(self, proposer_id: str) -> Optional[Block]:
        async with self._lock:
            account_nonces = {
                addr: self.chain.state.nonce_of(addr)
                for addr in self.chain.state.nonces
            }
            simple_txs  = self.mempool.select_simple(account_nonces, MAX_SIMPLE_TXS)
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
            proof = ConsensusProof(
                consensus_type = BlockType.POS,
                view           = 0,
                signatures     = [
                    (proposer_id, "dev"),
                    (proposer_id, "dev"),
                    (proposer_id, "dev"),
                ],
            )
            block = Block(header=header, simple_txs=simple_txs, consensus_proof=proof)
            try:
                self.chain.append(block)
                self.mempool.remove([tx.tx_id for tx in simple_txs])
                self._persist_block(block)
            except ValueError:
                return None

        # Broadcast outside the lock so peers can call ingest_block concurrently
        p2p = getattr(self, "_p2p_server", None)
        if p2p is not None:
            await p2p.broadcast_block(block.to_dict())
        return block

    # ── P2P block ingestion ────────────────────────────────────────────────────

    async def ingest_block(self, block: Block) -> dict:
        async with self._lock:
            try:
                self.chain.append(block)
                self.mempool.remove([tx.tx_id for tx in block.all_transactions])
                self._persist_block(block)
                return {"accepted": True, "reason": None}
            except ValueError as e:
                return {"accepted": False, "reason": str(e)}

    # ── Persistence helper ────────────────────────────────────────────────────

    def _persist_block(self, block: Block) -> None:
        """Save block + state to DB if persistence is enabled."""
        if self.db is None:
            return
        try:
            self.db.save_block(block)
            self.db.save_state(self.chain.state)
        except Exception as e:
            log.error("DB write failed at height %d: %s", block.height, e)

    # ── Peer management ────────────────────────────────────────────────────────

    def add_peer(self, base_url: str) -> None:
        self.peers.add(base_url.rstrip("/"))

    def remove_peer(self, base_url: str) -> None:
        self.peers.discard(base_url.rstrip("/"))


# ── Factories ─────────────────────────────────────────────────────────────────

def create_node_service(
    initial_allocations: dict[str, float] | None = None,
    initial_nodes:       list[dict] | None = None,
    f:                   int = DEFAULT_F,
) -> NodeService:
    """Bootstrap an in-memory NodeService (no persistence). Used in tests."""
    genesis = create_genesis_block(
        initial_allocations=initial_allocations,
        initial_nodes=initial_nodes,
    )
    chain = Chain(genesis, f=f)
    return NodeService(chain=chain)


def create_persistent_node_service(
    db_path:             str,
    initial_allocations: dict[str, float] | None = None,
    initial_nodes:       list[dict] | None = None,
    f:                   int = DEFAULT_F,
) -> NodeService:
    """Bootstrap a NodeService backed by SQLite persistence."""
    from core.storage.db import open_or_create_chain
    chain, db = open_or_create_chain(
        db_path             = db_path,
        initial_allocations = initial_allocations,
        initial_nodes       = initial_nodes,
        f                   = f,
    )
    return NodeService(chain=chain, db=db)
