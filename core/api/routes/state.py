"""
State routes — account balances, stakes, node registry, wallet history, faucet.

GET  /state/balance/{address}
GET  /state/node/{node_id}
GET  /state/nodes/active
GET  /state/nodes/dnn
GET  /state/nodes/pos
GET  /state/history/{address}
POST /state/faucet
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.api.deps import get_service
from core.api.node_service import NodeService
from core.api.schemas import BalanceResponse, NodeInfoResponse

router = APIRouter(prefix="/state", tags=["state"])

FAUCET_AMOUNT   = 10_000.0   # INFER dispensed per request
FAUCET_MAX_BAL  = 10_000.0   # only dispense when balance < this
_faucet_given: set[str] = set()  # addresses that already received faucet this session


class FaucetRequest(BaseModel):
    address: str


class FaucetResponse(BaseModel):
    success: bool
    amount:  float
    balance: float
    message: str


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


@router.get("/history/{address}", response_model=list[dict])
async def get_tx_history(address: str, limit: int = 50, svc: NodeService = Depends(get_service)):
    """Return confirmed transactions involving this address (sender or recipient)."""
    results = []
    for block in reversed(svc.chain.blocks):
        for tx in block.all_transactions:
            if tx.sender == address or tx.recipient == address:
                d = tx.to_dict()
                d["block_height"] = block.height
                d["block_hash"]   = block.hash
                d["status"]       = "confirmed"
                results.append(d)
                if len(results) >= limit:
                    return results
    return results


@router.post("/faucet", response_model=FaucetResponse)
async def faucet(body: FaucetRequest, svc: NodeService = Depends(get_service)):
    """
    Testnet faucet — dispenses INFER to any address with low balance.
    Limited to one grant per address per node session.
    """
    address = body.address.lower().strip()
    if len(address) != 40 or not all(c in "0123456789abcdef" for c in address):
        raise HTTPException(status_code=422, detail="Invalid address format (expected 40-char hex)")

    current_bal = svc.chain.state.balance_of(address)
    if address in _faucet_given:
        return FaucetResponse(
            success = False,
            amount  = 0.0,
            balance = current_bal,
            message = "Faucet already used for this address this session",
        )
    if current_bal >= FAUCET_MAX_BAL:
        return FaucetResponse(
            success = False,
            amount  = 0.0,
            balance = current_bal,
            message = f"Balance already ≥ {FAUCET_MAX_BAL:.0f} INFER",
        )

    # Direct state credit — testnet only, bypasses block system
    svc.chain.state.balances[address] = current_bal + FAUCET_AMOUNT
    _faucet_given.add(address)
    new_bal = svc.chain.state.balance_of(address)
    return FaucetResponse(
        success = True,
        amount  = FAUCET_AMOUNT,
        balance = new_bal,
        message = f"Dispensed {FAUCET_AMOUNT:.0f} INFER to {address[:8]}…",
    )
