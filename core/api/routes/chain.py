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


@router.get("/blocks", response_model=list[dict])
async def list_blocks(
    limit: int = 20,
    before: int | None = None,
    svc: NodeService = Depends(get_service),
):
    """
    Return up to `limit` block summaries ending at `before` height (exclusive).
    Default: most-recent `limit` blocks.
    """
    tip     = svc.chain.height
    end     = tip if before is None else min(before - 1, tip)
    start   = max(0, end - limit + 1)
    blocks  = []
    for h in range(end, start - 1, -1):
        b = svc.get_block(h)
        if b is None:
            continue
        blocks.append({
            "height":      b.header.height,
            "hash":        b.hash,
            "prev_hash":   b.header.prev_hash,
            "block_type":  b.header.block_type.value,
            "proposer_id": b.header.proposer_id,
            "tx_count":    len(b.all_transactions),
            "timestamp":   b.header.timestamp,
            "view":        b.header.view,
        })
    return blocks


@router.get("/stats", response_model=dict)
async def chain_stats(svc: NodeService = Depends(get_service)):
    """Aggregate chain statistics for the explorer dashboard."""
    chain   = svc.chain
    tip     = chain.height
    blocks  = chain.blocks  # in-memory list

    qoi_blocks   = sum(1 for b in blocks if b.header.block_type.value == "qoi")
    pos_blocks   = sum(1 for b in blocks if b.header.block_type.value == "pos")
    total_txs    = sum(len(b.all_transactions) for b in blocks)
    total_fees   = sum(
        sum(tx.fee for tx in b.simple_txs)
        for b in blocks
    )

    # Rough TPS: txs in last 60 s
    import time
    now      = time.time()
    recent   = [b for b in blocks if now - b.header.timestamp < 60]
    recent_txs = sum(len(b.all_transactions) for b in recent)
    tps      = round(recent_txs / 60, 3)

    # Average block time from last 10 blocks
    avg_block_time = None
    if len(blocks) >= 2:
        last10 = blocks[-min(10, len(blocks)):]
        diffs  = [
            last10[i].header.timestamp - last10[i-1].header.timestamp
            for i in range(1, len(last10))
        ]
        avg_block_time = round(sum(diffs) / len(diffs), 2) if diffs else None

    dnn_nodes = svc.chain.state.dnn_validators()
    pos_nodes = svc.chain.state.pos_validators()

    return {
        "chain_height":    tip,
        "total_blocks":    tip + 1,
        "qoi_blocks":      qoi_blocks,
        "pos_blocks":      pos_blocks,
        "total_txs":       total_txs,
        "total_fees":      round(total_fees, 4),
        "tps":             tps,
        "avg_block_time":  avg_block_time,
        "dnn_validators":  len(dnn_nodes),
        "pos_validators":  len(pos_nodes),
        "mempool_size":    svc.mempool.size,
        "tip_hash":        chain.tip.hash,
    }
