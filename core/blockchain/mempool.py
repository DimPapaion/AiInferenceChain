"""
Mempool — pending transaction queue for InferenceChain.

Selection policy:
  - Fee-priority: highest fee transactions are selected first
  - Nonce-ordered: per sender, only the next valid nonce is a candidate
  - Inference transactions are tracked separately (one per block)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .transaction import Transaction, TxType, TxFamily
from .constants import MEMPOOL_MAX_SIZE, MAX_SIMPLE_TXS


class Mempool:
    def __init__(self, max_size: int = MEMPOOL_MAX_SIZE) -> None:
        self.max_size = max_size

        # tx_id → Transaction for all pending txs
        self._pending: dict[str, Transaction] = {}

        # sender → list of txs sorted by nonce (ascending)
        self._by_sender: defaultdict[str, list[Transaction]] = defaultdict(list)

        # Inference requests queue (FIFO — one per block)
        self._inference_queue: list[Transaction] = []

    # ── Add ───────────────────────────────────────────────────────────────────

    def add(self, tx: Transaction) -> bool:
        """
        Add a transaction to the mempool.
        Returns True if accepted, False if rejected (full or duplicate).
        """
        if tx.tx_id in self._pending:
            return False  # duplicate

        if tx.family == TxFamily.INFERENCE:
            self._inference_queue.append(tx)
            self._pending[tx.tx_id] = tx
            return True

        if len(self._pending) >= self.max_size:
            return False  # mempool full

        self._pending[tx.tx_id] = tx
        sender_txs = self._by_sender[tx.sender]
        sender_txs.append(tx)
        sender_txs.sort(key=lambda t: t.nonce)
        return True

    # ── Select ────────────────────────────────────────────────────────────────

    def select_simple(
        self,
        account_nonces: dict[str, int],
        max_txs: int = MAX_SIMPLE_TXS,
    ) -> list[Transaction]:
        """
        Select up to max_txs simple transactions for a block.

        Rules:
          1. For each sender take only the next valid nonce tx (nonce = current + 1)
          2. Sort all candidates by fee descending
          3. Return top max_txs
        """
        candidates: list[Transaction] = []

        for sender, txs in self._by_sender.items():
            if not txs:
                continue
            current_nonce = account_nonces.get(sender, 0)
            for tx in txs:
                if tx.nonce == current_nonce + 1:
                    candidates.append(tx)
                    break   # only the next valid tx per sender

        candidates.sort(key=lambda t: t.fee, reverse=True)
        return candidates[:max_txs]

    def next_inference(self) -> Optional[Transaction]:
        """Pop the next pending inference request (FIFO)."""
        if self._inference_queue:
            tx = self._inference_queue.pop(0)
            self._pending.pop(tx.tx_id, None)
            return tx
        return None

    def peek_inference(self) -> Optional[Transaction]:
        """Look at the next inference request without removing it."""
        return self._inference_queue[0] if self._inference_queue else None

    # ── Remove ────────────────────────────────────────────────────────────────

    def remove(self, tx_ids: list[str]) -> None:
        """Remove committed or invalid transactions from the mempool."""
        for tx_id in tx_ids:
            tx = self._pending.pop(tx_id, None)
            if tx is None:
                continue
            if tx.family == TxFamily.SIMPLE:
                sender_txs = self._by_sender.get(tx.sender, [])
                self._by_sender[tx.sender] = [
                    t for t in sender_txs if t.tx_id != tx_id
                ]

    def clear_sender(self, sender: str, up_to_nonce: int) -> None:
        """Remove all txs from a sender with nonce <= up_to_nonce (post-commit cleanup)."""
        remaining = [
            tx for tx in self._by_sender.get(sender, [])
            if tx.nonce > up_to_nonce
        ]
        removed = [
            tx for tx in self._by_sender.get(sender, [])
            if tx.nonce <= up_to_nonce
        ]
        self._by_sender[sender] = remaining
        for tx in removed:
            self._pending.pop(tx.tx_id, None)

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._pending)

    @property
    def inference_pending(self) -> int:
        return len(self._inference_queue)

    def has_tx(self, tx_id: str) -> bool:
        return tx_id in self._pending

    def get_tx(self, tx_id: str) -> Optional[Transaction]:
        return self._pending.get(tx_id)

    def all_pending(self) -> list[Transaction]:
        return list(self._pending.values())

    def pending_for_sender(self, sender: str) -> list[Transaction]:
        return list(self._by_sender.get(sender, []))

    def __repr__(self) -> str:
        return (
            f"Mempool(size={self.size}, "
            f"inference_queue={self.inference_pending})"
        )
