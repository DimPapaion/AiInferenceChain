"""
P2P relay routes — used by peer nodes to push data to this node.

These are the HTTP-facing side of the gossip layer.
The real P2P server (WebSocket on p2p_port) handles direct node-to-node gossip.
These routes exist for:
  - Light clients that can't open WebSocket connections
  - Bootstrapping / peer registration via HTTP
  - Querying network status

POST /p2p/block        — peer pushes a new committed block
POST /p2p/tx           — peer relays a pending transaction
POST /p2p/consensus    — peer relays a consensus message (future)
POST /p2p/peers/add    — register a known peer
DELETE /p2p/peers/{url}
GET  /p2p/peers        — list known peers + connection status
GET  /p2p/status       — this node's summary (used for peer handshake)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import (
    PeerBlockRequest, PeerTxRequest, PeerConsensusMsg,
    P2PResponse, AddPeerRequest, PeerListResponse, NodeStatusResponse,
)
from core.blockchain.block import Block
from core.blockchain.transaction import Transaction

router = APIRouter(prefix="/p2p", tags=["p2p"])


@router.post("/block", response_model=P2PResponse)
async def ingest_block(body: PeerBlockRequest, svc: NodeService = Depends(get_service)):
    """
    A peer is pushing a block it has committed.
    We validate it against our chain state and append if valid.
    """
    try:
        block = Block.from_dict(body.block)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot deserialise block: {e}")

    result = await svc.ingest_block(block)

    # Also gossip via WebSocket P2P if the server is running
    p2p = getattr(svc, "_p2p_server", None)
    if p2p and result["accepted"]:
        await p2p.broadcast_block(body.block)

    return P2PResponse(**result)


@router.post("/tx", response_model=P2PResponse)
async def ingest_tx(body: PeerTxRequest, svc: NodeService = Depends(get_service)):
    """A peer is relaying a transaction."""
    try:
        tx = Transaction.from_dict(body.tx)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot deserialise tx: {e}")

    result = await svc.submit_tx(tx)

    p2p = getattr(svc, "_p2p_server", None)
    if p2p and result["accepted"]:
        await p2p.broadcast_tx(body.tx)

    return P2PResponse(accepted=result["accepted"], reason=result.get("reason"))


@router.post("/consensus", response_model=P2PResponse)
async def ingest_consensus_msg(
    body: PeerConsensusMsg,
    svc: NodeService = Depends(get_service),
):
    """
    Consensus message relay (VoteMsg, PrepareMsg, CommitMsg, ViewChangeMsg).
    Gossips via WebSocket P2P if server is running.
    """
    p2p = getattr(svc, "_p2p_server", None)
    if p2p:
        await p2p.broadcast_consensus(body.msg_type, body.payload)
    return P2PResponse(accepted=True, reason=None)


@router.post("/peers/add", response_model=PeerListResponse)
async def add_peer(body: AddPeerRequest, svc: NodeService = Depends(get_service)):
    svc.add_peer(body.url)
    # Trigger outbound connection if P2P server is running
    p2p = getattr(svc, "_p2p_server", None)
    if p2p:
        import asyncio
        asyncio.create_task(p2p._connect_outbound(body.url))
    return PeerListResponse(peers=sorted(svc.peers))


@router.delete("/peers/{peer_url:path}", response_model=PeerListResponse)
async def remove_peer(peer_url: str, svc: NodeService = Depends(get_service)):
    svc.remove_peer(peer_url)
    return PeerListResponse(peers=sorted(svc.peers))


@router.get("/peers", response_model=list[dict])
async def list_peers(request: Request, svc: NodeService = Depends(get_service)):
    """
    List known peers. If P2P server is running, includes live connection info.
    """
    p2p = getattr(svc, "_p2p_server", None)
    if p2p:
        return p2p.connected_peers()
    return [{"endpoint": url} for url in sorted(svc.peers)]


@router.get("/status", response_model=NodeStatusResponse)
async def node_status(request: Request, svc: NodeService = Depends(get_service)):
    """
    Handshake endpoint — a connecting peer calls this to learn our state.
    """
    app_state = request.app.state
    p2p = getattr(svc, "_p2p_server", None)
    return NodeStatusResponse(
        node_id      = getattr(app_state, "node_id", "unknown"),
        endpoint     = getattr(app_state, "endpoint", "unknown"),
        chain_height = svc.chain.height,
        tip_hash     = svc.chain.tip.hash,
        peer_count   = p2p.peer_count if p2p else len(svc.peers),
        mempool_size = svc.mempool.size,
    )
