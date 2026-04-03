"""
Unit tests for core/network/ — P2P message protocol, gossip dedup, peer tracking.

No real sockets used — tests drive the P2PServer internals directly.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from core.network.messages import (
    MsgType, P2PMessage,
    make_handshake, make_ping, make_pong,
    make_tx_msg, make_block_msg, make_consensus_msg,
    make_get_blocks, make_blocks_response, make_peers_msg,
)
from core.network.peer import PeerConnection
from core.network.p2p_server import P2PServer
from core.api.node_service import create_node_service

ALICE = "a" * 40
BOB   = "b" * 40

GENESIS_ALLOC = {ALICE: 500_000.0, BOB: 100_000.0}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_svc():
    return create_node_service(initial_allocations=GENESIS_ALLOC, f=1)


class FakeWS:
    """Minimal websocket stub for testing."""
    def __init__(self):
        self.sent: list[str] = []
        self.open = True
        self.closed = False

    async def send(self, data: str):
        self.sent.append(data)

    def last_msg(self) -> P2PMessage:
        return P2PMessage.decode(self.sent[-1])

    def all_msgs(self) -> list[P2PMessage]:
        return [P2PMessage.decode(m) for m in self.sent]


# ═════════════════════════════════════════════════════════════════════════════
# Message encoding / decoding
# ═════════════════════════════════════════════════════════════════════════════

class TestMessages:
    def test_handshake_roundtrip(self):
        msg = make_handshake("node1", "http://1.2.3.4:8000", 9000, 5, "a" * 64)
        restored = P2PMessage.decode(msg.encode())
        assert restored.type == MsgType.HANDSHAKE
        assert restored.payload["node_id"]      == "node1"
        assert restored.payload["chain_height"] == 5
        assert restored.payload["p2p_port"]     == 9000

    def test_ping_pong_roundtrip(self):
        ping = make_ping(12345.0)
        pong = make_pong(12345.0)
        assert P2PMessage.decode(ping.encode()).type == MsgType.PING
        assert P2PMessage.decode(pong.encode()).type == MsgType.PONG
        assert P2PMessage.decode(pong.encode()).payload["ts"] == 12345.0

    def test_tx_roundtrip(self):
        tx_dict = {"tx_id": "a" * 64, "tx_type": "stake", "sender": ALICE}
        msg = make_tx_msg(tx_dict)
        restored = P2PMessage.decode(msg.encode())
        assert restored.type == MsgType.TX
        assert restored.payload["tx_id"] == "a" * 64

    def test_block_roundtrip(self):
        block_dict = {"header": {"block_hash": "b" * 64, "height": 1}}
        msg = make_block_msg(block_dict)
        restored = P2PMessage.decode(msg.encode())
        assert restored.type == MsgType.BLOCK
        assert restored.payload["header"]["height"] == 1

    def test_consensus_roundtrip(self):
        msg = make_consensus_msg("VOTE", {"node_id": ALICE, "block_hash": "c" * 64})
        restored = P2PMessage.decode(msg.encode())
        assert restored.type == MsgType.CONSENSUS
        assert restored.payload["msg_type"] == "VOTE"

    def test_get_blocks_roundtrip(self):
        msg = make_get_blocks(3, 7)
        restored = P2PMessage.decode(msg.encode())
        assert restored.payload["from_height"] == 3
        assert restored.payload["to_height"]   == 7

    def test_peers_roundtrip(self):
        peers = ["http://1.2.3.4:8000", "http://5.6.7.8:8001"]
        msg = make_peers_msg(peers)
        restored = P2PMessage.decode(msg.encode())
        assert restored.payload["peers"] == peers

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            P2PMessage.decode('{"type": "INVALID", "payload": {}}')


# ═════════════════════════════════════════════════════════════════════════════
# PeerConnection
# ═════════════════════════════════════════════════════════════════════════════

class TestPeerConnection:
    def test_send_queues_message(self):
        ws = FakeWS()
        peer = PeerConnection(ws)
        asyncio.run(peer.send(make_ping(0.0)))
        assert len(ws.sent) == 1
        assert ws.last_msg().type == MsgType.PING

    def test_update_from_handshake(self):
        ws = FakeWS()
        peer = PeerConnection(ws)
        peer.update_from_handshake({
            "node_id":      "abc123",
            "endpoint":     "http://1.2.3.4:8000",
            "p2p_port":     9000,
            "chain_height": 10,
            "tip_hash":     "f" * 64,
        })
        assert peer.node_id      == "abc123"
        assert peer.chain_height == 10
        assert peer.handshake_done

    def test_is_alive_when_open(self):
        ws = FakeWS()
        peer = PeerConnection(ws)
        assert peer.is_alive

    def test_is_not_alive_when_closed(self):
        ws = FakeWS()
        ws.open   = False
        ws.closed = True
        peer = PeerConnection(ws)
        assert not peer.is_alive

    def test_send_failure_returns_false(self):
        class BrokenWS:
            open = False
            closed = True
            async def send(self, _): raise ConnectionError("gone")
        peer = PeerConnection(BrokenWS())
        result = asyncio.run(peer.send(make_ping(0.0)))
        assert result is False

    def test_to_dict(self):
        ws = FakeWS()
        peer = PeerConnection(ws, peer_url="http://1.2.3.4:8000", direction="outbound")
        d = peer.to_dict()
        assert d["direction"] == "outbound"
        assert "endpoint" in d


# ═════════════════════════════════════════════════════════════════════════════
# P2PServer — internal logic (no real sockets)
# ═════════════════════════════════════════════════════════════════════════════

class TestP2PServerGossip:
    def _make_server(self) -> P2PServer:
        svc = make_svc()
        return P2PServer(svc, node_id="test-node", endpoint="http://127.0.0.1:8000", p2p_port=9000)

    def test_seen_set_dedup(self):
        srv = self._make_server()
        assert not srv._already_seen("abc")
        srv._mark_seen("abc")
        assert srv._already_seen("abc")

    def test_seen_set_does_not_grow_beyond_max(self):
        from core.network.p2p_server import SEEN_SET_MAX
        srv = self._make_server()
        for i in range(SEEN_SET_MAX + 10):
            srv._mark_seen(str(i))
        # deque is capped at SEEN_SET_MAX
        assert len(srv._seen) <= SEEN_SET_MAX

    def test_to_ws_url_conversion(self):
        assert P2PServer._to_ws_url("http://1.2.3.4:8000") == "ws://1.2.3.4:9000"
        assert P2PServer._to_ws_url("http://localhost:8001") == "ws://localhost:9001"

    def test_to_ws_url_default_port(self):
        assert P2PServer._to_ws_url("http://mynode") == "ws://mynode:9000"

    def test_peer_count_zero_initially(self):
        srv = self._make_server()
        assert srv.peer_count == 0


# ═════════════════════════════════════════════════════════════════════════════
# P2PServer — message dispatch (async, no real sockets)
# ═════════════════════════════════════════════════════════════════════════════

class TestP2PDispatch:
    def _make_server_and_peer(self):
        svc = make_svc()
        srv = P2PServer(svc, node_id="srv", endpoint="http://0.0.0.0:8000", p2p_port=9000)
        ws  = FakeWS()
        peer = PeerConnection(ws, direction="inbound")
        return srv, peer, ws

    def test_dispatch_ping_sends_pong(self):
        srv, peer, ws = self._make_server_and_peer()
        msg = make_ping(99.0)
        asyncio.run(srv._dispatch(peer, msg))
        assert ws.last_msg().type == MsgType.PONG
        assert ws.last_msg().payload["ts"] == 99.0

    def test_dispatch_handshake_updates_peer(self):
        srv, peer, ws = self._make_server_and_peer()
        msg = make_handshake("peer-node", "http://1.2.3.4:8000", 9000, 0, "a" * 64)
        asyncio.run(srv._dispatch(peer, msg))
        assert peer.node_id      == "peer-node"
        assert peer.handshake_done

    def test_dispatch_handshake_requests_blocks_if_behind(self):
        srv, peer, ws = self._make_server_and_peer()
        # Peer claims height=5, we are at 0 — should send GET_BLOCKS
        msg = make_handshake("peer-node", "http://1.2.3.4:8000", 9000, 5, "a" * 64)
        asyncio.run(srv._dispatch(peer, msg))
        get_blocks = ws.last_msg()
        assert get_blocks.type == MsgType.GET_BLOCKS
        assert get_blocks.payload["from_height"] == 1

    def test_dispatch_get_blocks_serves_genesis(self):
        srv, peer, ws = self._make_server_and_peer()
        msg = make_get_blocks(0, 0)
        asyncio.run(srv._dispatch(peer, msg))
        response = ws.last_msg()
        assert response.type == MsgType.BLOCKS
        assert len(response.payload["blocks"]) == 1
        assert response.payload["blocks"][0]["header"]["height"] == 0

    def test_dispatch_get_blocks_out_of_range(self):
        srv, peer, ws = self._make_server_and_peer()
        msg = make_get_blocks(100, 200)
        asyncio.run(srv._dispatch(peer, msg))
        response = ws.last_msg()
        assert response.type == MsgType.BLOCKS
        assert response.payload["blocks"] == []

    def test_dispatch_tx_accepted(self):
        from core.blockchain.transaction import Transaction, TxType, TokenTransferPayload
        from core.blockchain.utils import now
        from core.node.identity import make_test_identity

        svc = make_svc()
        srv = P2PServer(svc, node_id="srv", endpoint="http://0.0.0.0:8000", p2p_port=9000)
        ws  = FakeWS()
        peer = PeerConnection(ws, direction="inbound")

        identity = make_test_identity(1)
        # Fund the sender in genesis
        svc.chain.state.balances[identity.address] = 50_000.0

        tx = Transaction(
            tx_type   = TxType.TOKEN_TRANSFER,
            sender    = identity.address,
            recipient = BOB,
            payload   = TokenTransferPayload(amount=100.0),
            nonce     = 1,
            fee       = 0.1,
            timestamp = now(),
        )
        tx.signature = identity.sign_tx(tx.tx_id)
        tx_dict = tx.to_dict()

        msg = make_tx_msg(tx_dict)
        asyncio.run(srv._dispatch(peer, msg))

        # tx should be in mempool
        assert svc.mempool.has_tx(tx.tx_id)

    def test_dispatch_tx_dedup(self):
        """Same tx received twice should only enter mempool once."""
        from core.blockchain.transaction import Transaction, TxType, TokenTransferPayload
        from core.blockchain.utils import now
        from core.node.identity import make_test_identity

        svc = make_svc()
        srv = P2PServer(svc, node_id="srv", endpoint="http://0.0.0.0:8000", p2p_port=9000)
        ws  = FakeWS()
        peer = PeerConnection(ws, direction="inbound")

        identity = make_test_identity(1)
        svc.chain.state.balances[identity.address] = 50_000.0

        tx = Transaction(
            tx_type=TxType.TOKEN_TRANSFER, sender=identity.address,
            recipient=BOB, payload=TokenTransferPayload(amount=100.0),
            nonce=1, fee=0.1, timestamp=now(),
        )
        tx.signature = identity.sign_tx(tx.tx_id)
        msg = make_tx_msg(tx.to_dict())

        asyncio.run(srv._dispatch(peer, msg))
        asyncio.run(srv._dispatch(peer, msg))  # duplicate

        # Still only 1 in mempool
        assert svc.mempool.size == 1

    def test_dispatch_peers_adds_to_service(self):
        srv, peer, ws = self._make_server_and_peer()
        msg = make_peers_msg(["http://10.0.0.1:8000", "http://10.0.0.2:8000"])
        asyncio.run(srv._dispatch(peer, msg))
        # Both URLs should be added to svc.peers
        assert "http://10.0.0.1:8000" in srv.svc.peers
        assert "http://10.0.0.2:8000" in srv.svc.peers
