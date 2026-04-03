"""
Chain routes — read-only ledger queries.

GET /chain/height
GET /chain/tip
GET /chain/block/{height}
GET /chain/block/hash/{block_hash}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import ChainHeightResponse, BlockResponse, BlockHeaderResponse

router = APIRouter(prefix="/chain", tags=["chain"])


def _serialise_block(block) -> BlockResponse:
    h = block.header
    return BlockResponse(
        header=BlockHeaderResponse(
            height      = h.height,
            hash        = block.hash,
            prev_hash   = h.prev_hash,
            timestamp   = h.timestamp,
            proposer_id = h.proposer_id,
            merkle_root = h.merkle_root,
            block_type  = h.block_type.value,
            view        = h.view,
        ),
        tx_count     = len(block.all_transactions),
        simple_txs   = [tx.to_dict() for tx in block.simple_txs],
        inference_tx = block.inference_tx.to_dict() if block.inference_tx else None,
        system_txs   = [tx.to_dict() for tx in block.system_txs],
        consensus    = {
            "type":       block.consensus_proof.consensus_type.value,
            "view":       block.consensus_proof.view,
            "signatures": block.consensus_proof.signatures,
        },
    )


@router.get("/height", response_model=ChainHeightResponse)
async def get_height(svc: NodeService = Depends(get_service)):
    tip = svc.chain.tip
    return ChainHeightResponse(height=svc.chain.height, tip_hash=tip.hash)


@router.get("/tip", response_model=BlockResponse)
async def get_tip(svc: NodeService = Depends(get_service)):
    return _serialise_block(svc.chain.tip)


@router.get("/block/{height}", response_model=BlockResponse)
async def get_block_by_height(height: int, svc: NodeService = Depends(get_service)):
    block = svc.get_block(height)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block at height {height} not found")
    return _serialise_block(block)


@router.get("/block/hash/{block_hash}", response_model=BlockResponse)
async def get_block_by_hash(block_hash: str, svc: NodeService = Depends(get_service)):
    block = svc.get_block_by_hash(block_hash)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block {block_hash[:8]}… not found")
    return _serialise_block(block)
