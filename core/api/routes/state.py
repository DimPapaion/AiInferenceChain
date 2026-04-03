"""
State routes — account balances, stakes, node registry.

GET /state/balance/{address}
GET /state/node/{node_id}
GET /state/nodes/active
GET /state/nodes/dnn
GET /state/nodes/pos
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import BalanceResponse, NodeInfoResponse

router = APIRouter(prefix="/state", tags=["state"])


@router.get("/balance/{address}", response_model=BalanceResponse)
async def get_balance(address: str, svc: NodeService = Depends(get_service)):
    return BalanceResponse(
        address    = address,
        balance    = svc.balance_of(address),
        stake      = svc.stake_of(address),
        reputation = svc.reputation_of(address),
        nonce      = svc.nonce_of(address),
    )


@router.get("/node/{node_id}", response_model=NodeInfoResponse)
async def get_node_info(node_id: str, svc: NodeService = Depends(get_service)):
    info = svc.get_node_info(node_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id[:8]}… not found")
    return NodeInfoResponse(**info)


@router.get("/nodes/active", response_model=list[NodeInfoResponse])
async def list_active_nodes(svc: NodeService = Depends(get_service)):
    return [NodeInfoResponse(**n) for n in svc.active_nodes()]


@router.get("/nodes/dnn", response_model=list[NodeInfoResponse])
async def list_dnn_validators(svc: NodeService = Depends(get_service)):
    return [NodeInfoResponse(**n) for n in svc.dnn_validators()]


@router.get("/nodes/pos", response_model=list[NodeInfoResponse])
async def list_pos_validators(svc: NodeService = Depends(get_service)):
    return [NodeInfoResponse(**n) for n in svc.pos_validators()]
