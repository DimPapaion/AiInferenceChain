"""
Inference routes — submit image inference requests, query results.

POST /inference/request
GET  /inference/{request_id}
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import (
    InferenceRequest, InferenceSubmitResponse, InferenceResultResponse,
)
from core.blockchain.transaction import (
    Transaction, TxType, InferenceRequestPayload,
)
from core.blockchain.utils import now

router = APIRouter(prefix="/inference", tags=["inference"])


@router.post("/request", response_model=InferenceSubmitResponse)
async def submit_inference(
    body: InferenceRequest,
    svc: NodeService = Depends(get_service),
):
    """
    Submit an image hash for decentralised inference.
    The node will include this as an INFERENCE_REQUEST tx in the next block,
    triggering a QoI consensus round among DNN validators.
    """
    # Derive a deterministic request_id
    request_id = hashlib.sha256(
        f"{body.image_hash}{body.sender}{body.nonce}".encode()
    ).hexdigest()

    tx = Transaction(
        tx_type   = TxType.INFERENCE_REQUEST,
        sender    = body.sender,
        payload   = InferenceRequestPayload(
            request_id = request_id,
            image_hash = body.image_hash,
            model_hint = body.model_hint,
        ),
        nonce     = body.nonce,
        fee       = body.fee,
        timestamp = now(),
        signature = body.signature,
    )

    result = await svc.submit_tx(tx)
    return InferenceSubmitResponse(
        accepted   = result["accepted"],
        request_id = request_id,
        tx_id      = tx.tx_id,
        reason     = result.get("reason"),
    )


@router.get("/{request_id}", response_model=InferenceResultResponse)
async def get_inference_result(
    request_id: str,
    svc: NodeService = Depends(get_service),
):
    result = svc.get_inference_result(request_id)
    if result is None:
        # Check if it's still pending in the mempool
        pending = next(
            (tx for tx in svc.mempool.all_pending()
             if tx.tx_type == TxType.INFERENCE_REQUEST
             and tx.payload.request_id == request_id),
            None,
        )
        if pending:
            return InferenceResultResponse(request_id=request_id, status="pending")
        raise HTTPException(status_code=404, detail=f"Inference request {request_id[:8]}… not found")

    return InferenceResultResponse(
        request_id          = request_id,
        status              = "confirmed",
        final_class         = result.get("final_class"),
        confidence          = result.get("confidence"),
        participating_nodes = result.get("participating_nodes"),
    )
