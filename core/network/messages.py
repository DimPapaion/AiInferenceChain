"""
P2P wire message protocol for InferenceChain.

All messages are JSON objects with a top-level "type" field.
Sent over persistent WebSocket connections between nodes.

Message flow diagram:
  Connect  →  HANDSHAKE (both)  →  [GET_BLOCKS if behind]  →  BLOCKS
  Running  →  TX / BLOCK / CONSENSUS gossip
  Periodic →  PING / PONG keepalive
  Periodic →  PEERS exchange
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MsgType(str, Enum):
    # ── Handshake ─────────────────────────────────────────────────────────────
    HANDSHAKE      = "HANDSHAKE"      # on connect: exchange chain state + identity
    # ── Keepalive ─────────────────────────────────────────────────────────────
    PING           = "PING"
    PONG           = "PONG"
    # ── Gossip ────────────────────────────────────────────────────────────────
    TX             = "TX"             # broadcast a single pending transaction
    BLOCK          = "BLOCK"          # broadcast a newly committed block
    CONSENSUS      = "CONSENSUS"      # relay a consensus message (Vote/Prepare/Commit)
    # ── Sync ──────────────────────────────────────────────────────────────────
    GET_BLOCKS     = "GET_BLOCKS"     # request a range of blocks
    BLOCKS         = "BLOCKS"         # response: list of serialised blocks
    # ── Peer exchange ─────────────────────────────────────────────────────────
    PEERS          = "PEERS"          # share known peer base-URLs
    # ── Decentralised image store ─────────────────────────────────────────────
    IMAGE_REQUEST  = "IMAGE_REQUEST"  # "does anyone have image <hash>?"
    IMAGE_RESPONSE = "IMAGE_RESPONSE" # "here are the bytes for <hash>"


@dataclass
class P2PMessage:
    """
    Top-level wrapper for all P2P wire messages.
    Encoded as: {"type": "<MsgType>", "payload": {...}}
    """
    type:    MsgType
    payload: dict[str, Any]

    def encode(self) -> str:
        return json.dumps({"type": self.type.value, "payload": self.payload})

    @classmethod
    def decode(cls, raw: str) -> P2PMessage:
        d = json.loads(raw)
        return cls(type=MsgType(d["type"]), payload=d.get("payload", {}))


# ── Payload constructors (thin helpers) ───────────────────────────────────────

def make_handshake(
    node_id:      str,
    endpoint:     str,
    p2p_port:     int,
    chain_height: int,
    tip_hash:     str,
) -> P2PMessage:
    return P2PMessage(
        type    = MsgType.HANDSHAKE,
        payload = {
            "node_id":      node_id,
            "endpoint":     endpoint,
            "p2p_port":     p2p_port,
            "chain_height": chain_height,
            "tip_hash":     tip_hash,
        },
    )


def make_ping(ts: float) -> P2PMessage:
    return P2PMessage(type=MsgType.PING, payload={"ts": ts})


def make_pong(ts: float) -> P2PMessage:
    return P2PMessage(type=MsgType.PONG, payload={"ts": ts})


def make_tx_msg(tx_dict: dict) -> P2PMessage:
    return P2PMessage(type=MsgType.TX, payload=tx_dict)


def make_block_msg(block_dict: dict) -> P2PMessage:
    return P2PMessage(type=MsgType.BLOCK, payload=block_dict)


def make_consensus_msg(msg_type: str, data: dict) -> P2PMessage:
    return P2PMessage(
        type    = MsgType.CONSENSUS,
        payload = {"msg_type": msg_type, "data": data},
    )


def make_get_blocks(from_height: int, to_height: int) -> P2PMessage:
    return P2PMessage(
        type    = MsgType.GET_BLOCKS,
        payload = {"from_height": from_height, "to_height": to_height},
    )


def make_blocks_response(blocks: list[dict]) -> P2PMessage:
    return P2PMessage(type=MsgType.BLOCKS, payload={"blocks": blocks})


def make_peers_msg(peers: list[str]) -> P2PMessage:
    return P2PMessage(type=MsgType.PEERS, payload={"peers": peers})


def make_image_request(image_hash: str) -> P2PMessage:
    return P2PMessage(
        type    = MsgType.IMAGE_REQUEST,
        payload = {"image_hash": image_hash},
    )


def make_image_response(image_hash: str, data_hex: str) -> P2PMessage:
    return P2PMessage(
        type    = MsgType.IMAGE_RESPONSE,
        payload = {"image_hash": image_hash, "data_hex": data_hex},
    )
