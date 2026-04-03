"""
core.network — P2P gossip layer for InferenceChain.

Each running node creates one P2PServer instance, shared with the
FastAPI app via the same NodeService singleton.

Quick start:
    from core.network import P2PServer
    p2p = P2PServer(node_service, node_id=..., endpoint=..., p2p_port=9000)
    p2p.add_bootstrap("http://seed.inferencechain.net:8000")
    await p2p.start()   # runs forever (use asyncio.create_task)
"""

from core.network.messages import (
    MsgType, P2PMessage,
    make_handshake, make_ping, make_pong,
    make_tx_msg, make_block_msg, make_consensus_msg,
    make_get_blocks, make_blocks_response, make_peers_msg,
)
from core.network.peer import PeerConnection
from core.network.p2p_server import P2PServer

__all__ = [
    "P2PServer", "PeerConnection",
    "MsgType", "P2PMessage",
    "make_handshake", "make_ping", "make_pong",
    "make_tx_msg", "make_block_msg", "make_consensus_msg",
    "make_get_blocks", "make_blocks_response", "make_peers_msg",
]
