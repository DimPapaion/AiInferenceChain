"""
Pydantic schemas for InferenceChain REST API.

Separates wire format (API) from internal domain objects.
All amounts are in INFER tokens (float).
All addresses/hashes are hex strings.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Common ────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ── Chain ─────────────────────────────────────────────────────────────────────

class ChainHeightResponse(BaseModel):
    height: int
    tip_hash: str


class BlockHeaderResponse(BaseModel):
    height:      int
    hash:        str
    prev_hash:   str
    timestamp:   float
    proposer_id: str
    merkle_root: str
    block_type:  str
    view:        int


class BlockResponse(BaseModel):
    header:       BlockHeaderResponse
    tx_count:     int
    simple_txs:   list[dict]
    inference_tx: Optional[dict]
    system_txs:   list[dict]
    consensus:    dict


# ── State ─────────────────────────────────────────────────────────────────────

class BalanceResponse(BaseModel):
    address:    str
    balance:    float
    stake:      float
    reputation: float
    nonce:      int


class NodeInfoResponse(BaseModel):
    node_id:       str
    address:       str
    node_type:     str
    endpoint:      str
    is_active:     bool
    pom_verified:  bool
    model_name:    Optional[str] = None
    weights_hash:  Optional[str] = None
    dataset_id:    Optional[str] = None
    registered_at: int


# ── Transactions ──────────────────────────────────────────────────────────────

class SubmitTxRequest(BaseModel):
    """
    Raw signed transaction in wire format.
    The client builds and signs the tx, then POSTs the serialised dict here.
    Matches Transaction.to_dict() exactly.
    """
    tx_type:   str
    sender:    str
    payload:   dict[str, Any]
    nonce:     int
    fee:       float = 0.0
    recipient: Optional[str] = None
    timestamp: float
    signature: Optional[str] = None
    tx_id:     str


class SubmitTxResponse(BaseModel):
    accepted: bool
    tx_id:    str
    reason:   Optional[str] = None


class TxStatusResponse(BaseModel):
    tx_id:        str
    status:       str          # "pending" | "confirmed" | "not_found"
    tx_type:      Optional[str]    = None
    sender:       Optional[str]    = None
    block_height: Optional[int]    = None
    block_hash:   Optional[str]    = None
    payload:      Optional[dict]   = None


# ── Inference ─────────────────────────────────────────────────────────────────

class InferenceRequest(BaseModel):
    """Client submits an image hash + model hint to trigger a QoI round."""
    image_hash: str = Field(..., min_length=64, max_length=64,
                            description="SHA-256 hex of the raw image bytes")
    model_hint: str = Field(default="any",
                            description="Preferred model name, or 'any'")
    sender:     str = Field(..., min_length=40, max_length=40,
                            description="Requesting client address")
    nonce:      int
    fee:        float = Field(default=1.0, ge=0.0)
    signature:  Optional[str] = None


class InferenceSubmitResponse(BaseModel):
    accepted:   bool
    request_id: str
    tx_id:      str
    reason:     Optional[str] = None


class InferenceResultResponse(BaseModel):
    request_id:          str
    status:              str       # "pending" | "confirmed"
    final_class:         Optional[int]         = None
    confidence:          Optional[float]       = None
    participating_nodes: Optional[list[str]]   = None


# ── P2P relay (used by peer nodes) ────────────────────────────────────────────

class PeerBlockRequest(BaseModel):
    """A peer is pushing a serialised block."""
    block: dict[str, Any]


class PeerTxRequest(BaseModel):
    """A peer is relaying a transaction."""
    tx: dict[str, Any]


class PeerConsensusMsg(BaseModel):
    """A peer is relaying a consensus message (VoteMsg, PrepareMsg, etc.)."""
    msg_type: str
    payload:  dict[str, Any]


class P2PResponse(BaseModel):
    accepted: bool
    reason:   Optional[str] = None


# ── Peers ─────────────────────────────────────────────────────────────────────

class AddPeerRequest(BaseModel):
    url: str = Field(..., description="Base URL of the peer node, e.g. http://1.2.3.4:8000")


class PeerListResponse(BaseModel):
    peers: list[str]


# ── Node info (self-description) ──────────────────────────────────────────────

class NodeStatusResponse(BaseModel):
    node_id:      str
    endpoint:     str
    chain_height: int
    tip_hash:     str
    peer_count:   int
    mempool_size: int
