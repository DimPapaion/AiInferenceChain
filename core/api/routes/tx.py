"""
Transaction routes — submit and query transactions.

POST /tx/submit
GET  /tx/{tx_id}
GET  /tx/pending          — mempool snapshot
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import (
    SubmitTxRequest, SubmitTxResponse, TxStatusResponse,
)
from core.blockchain.transaction import Transaction

router = APIRouter(prefix="/tx", tags=["transactions"])


@router.post("/submit", response_model=SubmitTxResponse)
async def submit_tx(body: SubmitTxRequest, svc: NodeService = Depends(get_service)):
    """
    Accept a pre-built, pre-signed transaction from a client or peer.
    The client is responsible for building and signing the tx using the SDK.
    """
    try:
        tx = Transaction.from_dict(body.model_dump())
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot deserialise transaction: {e}")

    result = await svc.submit_tx(tx)
    return SubmitTxResponse(**result)


@router.get("/pending", response_model=list[dict])
async def list_pending(svc: NodeService = Depends(get_service)):
    """Return all pending transactions in the mempool."""
    return [tx.to_dict() for tx in svc.mempool.all_pending()]


@router.get("/{tx_id}", response_model=TxStatusResponse)
async def get_tx(tx_id: str, svc: NodeService = Depends(get_service)):
    result = svc.get_tx(tx_id)
    if result is None:
        return TxStatusResponse(tx_id=tx_id, status="not_found")
    return TxStatusResponse(
        tx_id        = tx_id,
        status       = result["status"],
        tx_type      = result.get("tx_type"),
        sender       = result.get("sender"),
        block_height = result.get("block_height"),
        block_hash   = result.get("block_hash"),
        payload      = result.get("payload"),
    )
