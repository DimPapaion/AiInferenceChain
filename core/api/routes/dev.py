"""
Dev routes — only available in dev/single-node mode.
Used to manually trigger block sealing without a full consensus engine.

POST /dev/seal          — seal a block from current mempool contents
GET  /dev/mempool       — mempool stats
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import get_service
from core.api.node_service import NodeService

router = APIRouter(prefix="/dev", tags=["dev"])

GENESIS_ADDRESS = "0" * 40


@router.post("/seal")
async def seal_block(
    proposer_id: str = GENESIS_ADDRESS,
    svc: NodeService = Depends(get_service),
):
    """
    Manually seal a PoS block from the current mempool.
    In production this is triggered by the consensus engine after 2f+1 votes.
    """
    block = await svc.seal_block(proposer_id)
    if block is None:
        raise HTTPException(status_code=400, detail="Block sealing failed (validation error)")
    return {
        "sealed":     True,
        "height":     block.height,
        "hash":       block.hash,
        "tx_count":   len(block.all_transactions),
        "block_type": block.header.block_type.value,
    }


@router.get("/mempool")
async def mempool_stats(svc: NodeService = Depends(get_service)):
    return {
        "size":             svc.mempool.size,
        "inference_pending": svc.mempool.inference_pending,
        "pending_txs":      [tx.to_dict() for tx in svc.mempool.all_pending()],
    }
