"""
Unit tests for core/blockchain/mempool.py
"""

import pytest
from core.blockchain import (
    Mempool, Transaction, TxType,
    TokenTransferPayload, InferenceRequestPayload,
)

ALICE = "a" * 40
BOB   = "b" * 40


def make_transfer(sender=ALICE, recipient=BOB, amount=10.0, nonce=1, fee=1.0):
    return Transaction(
        tx_type   = TxType.TOKEN_TRANSFER,
        sender    = sender,
        recipient = recipient,
        payload   = TokenTransferPayload(amount=amount),
        nonce     = nonce,
        fee       = fee,
    )

def make_inference(request_id="req-001"):
    return Transaction(
        tx_type = TxType.INFERENCE_REQUEST,
        sender  = ALICE,
        payload = InferenceRequestPayload(
            request_id=request_id,
            image_hash="f" * 64,
            model_hint="any",
        ),
        nonce = 1,
    )


class TestMempoolAdd:
    def test_add_simple_tx(self):
        pool = Mempool()
        tx   = make_transfer()
        assert pool.add(tx) is True
        assert pool.size == 1

    def test_duplicate_rejected(self):
        pool = Mempool()
        tx   = make_transfer()
        pool.add(tx)
        assert pool.add(tx) is False
        assert pool.size == 1

    def test_mempool_full_rejects(self):
        pool = Mempool(max_size=2)
        pool.add(make_transfer(nonce=1))
        pool.add(make_transfer(nonce=2))
        pool.add(make_transfer(sender=BOB, nonce=1))   # 3rd — should fail
        assert pool.size == 2

    def test_add_inference_tx(self):
        pool = Mempool()
        tx   = make_inference()
        assert pool.add(tx) is True
        assert pool.inference_pending == 1


class TestMempoolSelect:
    def test_select_simple_respects_nonce(self):
        pool = Mempool()
        # Add nonce=2 first, then nonce=1
        pool.add(make_transfer(nonce=2, fee=5.0))
        pool.add(make_transfer(nonce=1, fee=1.0))
        # Only nonce=1 should be selected (current account nonce is 0)
        selected = pool.select_simple(account_nonces={ALICE: 0})
        assert len(selected) == 1
        assert selected[0].nonce == 1

    def test_select_simple_fee_priority(self):
        pool = Mempool()
        pool.add(make_transfer(sender=ALICE, nonce=1, fee=1.0))
        pool.add(make_transfer(sender=BOB,   nonce=1, fee=5.0))
        selected = pool.select_simple(account_nonces={ALICE: 0, BOB: 0})
        assert selected[0].sender == BOB    # higher fee first

    def test_select_simple_max_limit(self):
        pool = Mempool()
        for i in range(10):
            sender = hex(i)[2:].zfill(40)
            pool.add(make_transfer(sender=sender, nonce=1, fee=float(i)))
        selected = pool.select_simple(
            account_nonces={hex(i)[2:].zfill(40): 0 for i in range(10)},
            max_txs=3,
        )
        assert len(selected) == 3

    def test_select_does_not_remove_txs(self):
        pool = Mempool()
        pool.add(make_transfer(nonce=1))
        pool.select_simple(account_nonces={ALICE: 0})
        assert pool.size == 1  # still there until remove() is called


class TestMempoolInference:
    def test_next_inference_fifo(self):
        pool = Mempool()
        pool.add(make_inference("req-001"))
        pool.add(make_inference("req-002"))
        first  = pool.next_inference()
        second = pool.next_inference()
        assert first.payload.request_id  == "req-001"
        assert second.payload.request_id == "req-002"

    def test_next_inference_none_when_empty(self):
        pool = Mempool()
        assert pool.next_inference() is None

    def test_peek_does_not_consume(self):
        pool = Mempool()
        pool.add(make_inference("req-001"))
        pool.peek_inference()
        assert pool.inference_pending == 1


class TestMempoolRemove:
    def test_remove_committed_txs(self):
        pool = Mempool()
        tx   = make_transfer(nonce=1)
        pool.add(tx)
        pool.remove([tx.tx_id])
        assert pool.size == 0

    def test_clear_sender_removes_up_to_nonce(self):
        pool = Mempool()
        pool.add(make_transfer(nonce=1))
        pool.add(make_transfer(nonce=2))
        pool.add(make_transfer(nonce=3))
        pool.clear_sender(ALICE, up_to_nonce=2)
        remaining = pool.pending_for_sender(ALICE)
        assert len(remaining) == 1
        assert remaining[0].nonce == 3
