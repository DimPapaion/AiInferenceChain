"""
P2PServer — WebSocket-based gossip layer for InferenceChain.

Each node runs one P2PServer instance. It handles:
  1. Inbound connections  (peers connect to us on p2p_port)
  2. Outbound connections (we connect to known peers)
  3. Message dispatch     (HANDSHAKE → PING/PONG → TX/BLOCK/CONSENSUS/SYNC)
  4. Gossip deduplication (seen-set prevents re-broadcasting the same message)
  5. Chain sync           (on connect, request missing blocks from ahead peers)
  6. Peer exchange        (periodically share our known-peer list)

Wire format: JSON over WebSocket (see core/network/messages.py)

Concurrency model:
  - One asyncio task per peer connection (reader loop)
  - Gossip broadcast is fire-and-forget (asyncio.create_task)
  - NodeService access goes through its own asyncio.Lock
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

from core.network.messages import (
    MsgType, P2PMessage,
    make_handshake, make_ping, make_pong,
    make_tx_msg, make_block_msg,
    make_get_blocks, make_blocks_response,
    make_peers_msg, make_consensus_msg,
)
from core.network.peer import PeerConnection

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PING_INTERVAL    = 30.0      # seconds between PING messages
PEER_SHARE_INTERVAL = 60.0   # seconds between PEERS exchange
SEEN_SET_MAX     = 10_000    # max entries in gossip dedup set
MAX_BLOCKS_PER_REQUEST = 50  # max blocks returned in one BLOCKS response
MAX_PEERS        = 50        # max outbound connections


class P2PServer:
    """
    Full P2P gossip server for a single InferenceChain node.
    """

    def __init__(
        self,
        node_service,          # core.api.node_service.NodeService
        node_id:   str,
        endpoint:  str,        # this node's REST base URL, e.g. "http://1.2.3.4:8000"
        p2p_port:  int = 30303,
        host:      str = "0.0.0.0",
    ) -> None:
        self.svc       = node_service
        self.node_id   = node_id
        self.endpoint  = endpoint
        self.p2p_port  = p2p_port
        self.host      = host

        # Active peer connections: websocket_id → PeerConnection
        self._peers: dict[int, PeerConnection] = {}
        self._peers_lock = asyncio.Lock()

        # Gossip dedup — rolling window of recently seen hashes
        self._seen: deque[str] = deque(maxlen=SEEN_SET_MAX)
        self._seen_set: set[str] = set()

        # Bootstrap peer URLs to connect to on startup
        self._bootstrap_urls: list[str] = []

        # Peer discovery (set via attach_discovery)
        self._discovery = None

        # Consensus engine (set via attach_consensus)
        self._consensus_engine = None

        # Background tasks
        self._tasks: list[asyncio.Task] = []
        self._server = None

    # ── Public interface ──────────────────────────────────────────────────────

    def attach_discovery(self, discovery) -> None:
        """Wire a PeerDiscovery instance for persistent peer tracking."""
        self._discovery = discovery
        # Seed bootstrap URLs from the discovery list
        for url in discovery.seed_peers():
            if url not in self._bootstrap_urls:
                self._bootstrap_urls.append(url)

    def attach_consensus(self, engine) -> None:
        """Wire the ConsensusEngine so incoming consensus msgs are routed to it."""
        self._consensus_engine = engine

    def add_bootstrap(self, base_url: str) -> None:
        """Register a peer URL to connect to on startup."""
        self._bootstrap_urls.append(base_url.rstrip("/"))

    async def start(self) -> None:
        """
        Start the WebSocket server and connect to bootstrap peers.
        Call this once from the node runner (runs forever until cancelled).
        """
        self._server = await websockets.serve(
            self._handle_inbound,
            self.host,
            self.p2p_port,
        )
        log.info("P2P server listening on %s:%d", self.host, self.p2p_port)

        # Connect to bootstrap peers
        for url in self._bootstrap_urls:
            asyncio.create_task(self._connect_outbound(url))

        # Background maintenance tasks
        self._tasks.append(asyncio.create_task(self._ping_loop()))
        self._tasks.append(asyncio.create_task(self._peer_share_loop()))

        await self._server.wait_closed()

    async def stop(self) -> None:
        """Graceful shutdown."""
        for task in self._tasks:
            task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ── Gossip: broadcast to all peers ────────────────────────────────────────

    async def broadcast_tx(self, tx_dict: dict) -> None:
        key = tx_dict.get("tx_id", "")
        if self._already_seen(key):
            return
        self._mark_seen(key)
        await self._broadcast(make_tx_msg(tx_dict))

    async def broadcast_block(self, block_dict: dict) -> None:
        key = block_dict.get("header", {}).get("block_hash", "")
        if self._already_seen(key):
            return
        self._mark_seen(key)
        await self._broadcast(make_block_msg(block_dict))

    async def broadcast_consensus(self, msg_type: str, data: dict) -> None:
        msg = make_consensus_msg(msg_type, data)
        await self._broadcast(msg)

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    def connected_peers(self) -> list[dict]:
        return [p.to_dict() for p in self._peers.values()]

    # ── Inbound connection handler ────────────────────────────────────────────

    async def _handle_inbound(self, websocket) -> None:
        peer = PeerConnection(websocket, direction="inbound")
        await self._run_peer(peer)

    # ── Outbound connection (we dial a peer) ─────────────────────────────────

    async def _connect_outbound(self, base_url: str, retries: int = 5) -> None:
        """
        Attempt to connect to a peer's P2P port.
        The P2P port is discovered via /p2p/status if needed,
        but for now we assume p2p_port = REST_port + 1000 as convention,
        OR the caller passes the full ws:// URL.
        """
        # Convert http://host:port → ws://host:(port+1000)
        ws_url = self._to_ws_url(base_url)
        attempt = 0
        while attempt < retries:
            try:
                log.info("Connecting to peer %s (attempt %d)", ws_url, attempt + 1)
                async with websockets.connect(ws_url) as ws:
                    peer = PeerConnection(ws, peer_url=base_url, direction="outbound")
                    self.svc.add_peer(base_url)
                    await self._run_peer(peer)
                return   # clean disconnect
            except Exception as e:
                attempt += 1
                wait = min(2 ** attempt, 30)
                log.warning("Peer %s unreachable: %s — retry in %ds", ws_url, e, wait)
                await asyncio.sleep(wait)
        log.error("Gave up connecting to %s after %d attempts", ws_url, retries)

    # ── Per-peer message loop ─────────────────────────────────────────────────

    async def _run_peer(self, peer: PeerConnection) -> None:
        """Main read loop for a single peer connection."""
        # Register peer
        peer_key = id(peer.ws)
        async with self._peers_lock:
            self._peers[peer_key] = peer

        # Send our handshake immediately
        await peer.send(make_handshake(
            node_id      = self.node_id,
            endpoint     = self.endpoint,
            p2p_port     = self.p2p_port,
            chain_height = self.svc.chain.height,
            tip_hash     = self.svc.chain.tip.hash,
        ))

        try:
            async for raw in peer.ws:
                peer.touch()
                try:
                    msg = P2PMessage.decode(raw)
                    peer.bytes_recv += len(raw)
                    await self._dispatch(peer, msg)
                except Exception as e:
                    log.warning("Bad message from %s: %s", peer.short_id, e)
        except ConnectionClosed:
            log.info("Peer %s disconnected", peer.short_id)
        except Exception as e:
            log.warning("Peer %s error: %s", peer.short_id, e)
        finally:
            async with self._peers_lock:
                self._peers.pop(peer_key, None)
            log.debug("Removed peer %s", peer.short_id)

    # ── Message dispatch ──────────────────────────────────────────────────────

    async def _dispatch(self, peer: PeerConnection, msg: P2PMessage) -> None:
        match msg.type:
            case MsgType.HANDSHAKE:
                await self._on_handshake(peer, msg.payload)
            case MsgType.PING:
                await peer.send(make_pong(msg.payload.get("ts", 0.0)))
            case MsgType.PONG:
                peer.touch()
            case MsgType.TX:
                await self._on_tx(peer, msg.payload)
            case MsgType.BLOCK:
                await self._on_block(peer, msg.payload)
            case MsgType.CONSENSUS:
                await self._on_consensus(peer, msg.payload)
            case MsgType.GET_BLOCKS:
                await self._on_get_blocks(peer, msg.payload)
            case MsgType.BLOCKS:
                await self._on_blocks(peer, msg.payload)
            case MsgType.PEERS:
                await self._on_peers(peer, msg.payload)
            case _:
                log.debug("Unknown message type %s from %s", msg.type, peer.short_id)

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _on_handshake(self, peer: PeerConnection, payload: dict) -> None:
        peer.update_from_handshake(payload)
        log.info(
            "Handshake with %s — their height=%d  ours=%d",
            peer.short_id, peer.chain_height, self.svc.chain.height,
        )
        # If they're ahead, ask for missing blocks
        our_height = self.svc.chain.height
        if peer.chain_height > our_height:
            await peer.send(make_get_blocks(
                from_height = our_height + 1,
                to_height   = min(peer.chain_height, our_height + MAX_BLOCKS_PER_REQUEST),
            ))

    async def _on_tx(self, peer: PeerConnection, tx_dict: dict) -> None:
        tx_id = tx_dict.get("tx_id", "")
        if self._already_seen(tx_id):
            return
        self._mark_seen(tx_id)

        try:
            from core.blockchain.transaction import Transaction
            tx = Transaction.from_dict(tx_dict)
            await self.svc.submit_tx(tx)
        except Exception as e:
            log.debug("Rejected tx %s from %s: %s", tx_id[:8], peer.short_id, e)
            return

        # Gossip forward to other peers
        await self._broadcast(make_tx_msg(tx_dict), exclude=id(peer.ws))

    async def _on_block(self, peer: PeerConnection, block_dict: dict) -> None:
        block_hash = block_dict.get("header", {}).get("block_hash", "")
        if self._already_seen(block_hash):
            return
        self._mark_seen(block_hash)

        try:
            from core.blockchain.block import Block
            block = Block.from_dict(block_dict)
            result = await self.svc.ingest_block(block)
            if result["accepted"]:
                log.info(
                    "Accepted block height=%d hash=%s from %s",
                    block.height, block_hash[:8], peer.short_id,
                )
                # Update peer's known chain state
                peer.update_chain_state(block.height, block_hash)
                # Gossip forward
                await self._broadcast(make_block_msg(block_dict), exclude=id(peer.ws))
            else:
                log.debug("Rejected block %s: %s", block_hash[:8], result["reason"])
        except Exception as e:
            log.warning("Block from %s failed: %s", peer.short_id, e)

    async def _on_consensus(self, peer: PeerConnection, payload: dict) -> None:
        """Route consensus messages to the ConsensusEngine and gossip forward."""
        msg_type = payload.get("msg_type", "")
        data     = payload.get("data", {})
        log.debug("Consensus msg %s from %s", msg_type, peer.short_id)

        # Route to consensus engine if running
        if self._consensus_engine is not None:
            asyncio.create_task(
                self._consensus_engine.handle_consensus_msg(msg_type, data)
            )

        # Gossip forward — all nodes in the consensus round need to see it
        await self._broadcast(
            make_consensus_msg(msg_type, data),
            exclude=id(peer.ws),
        )

    async def _on_get_blocks(self, peer: PeerConnection, payload: dict) -> None:
        from_h = payload.get("from_height", 0)
        to_h   = min(
            payload.get("to_height", from_h),
            from_h + MAX_BLOCKS_PER_REQUEST - 1,
        )
        blocks = []
        for h in range(from_h, to_h + 1):
            block = self.svc.get_block(h)
            if block is None:
                break
            blocks.append(block.to_dict())

        await peer.send(make_blocks_response(blocks))
        log.debug(
            "Served %d blocks (%d–%d) to %s",
            len(blocks), from_h, to_h, peer.short_id,
        )

    async def _on_blocks(self, peer: PeerConnection, payload: dict) -> None:
        """Process a batch of blocks received from a peer (sync response)."""
        from core.blockchain.block import Block
        blocks_raw = payload.get("blocks", [])
        accepted = 0
        for block_dict in blocks_raw:
            block_hash = block_dict.get("header", {}).get("block_hash", "")
            if self._already_seen(block_hash):
                continue
            try:
                block = Block.from_dict(block_dict)
                result = await self.svc.ingest_block(block)
                if result["accepted"]:
                    self._mark_seen(block_hash)
                    accepted += 1
                    log.info("Synced block height=%d from %s", block.height, peer.short_id)
                else:
                    log.debug("Sync block rejected: %s", result["reason"])
            except Exception as e:
                log.warning("Sync block error from %s: %s", peer.short_id, e)

        if accepted:
            # If we're still behind, ask for more
            our_height   = self.svc.chain.height
            peer_height  = peer.chain_height
            if peer_height > our_height:
                await peer.send(make_get_blocks(
                    from_height = our_height + 1,
                    to_height   = min(peer_height, our_height + MAX_BLOCKS_PER_REQUEST),
                ))

    async def _on_peers(self, peer: PeerConnection, payload: dict) -> None:
        """Process a peer-list message — connect to any new peers."""
        for url in payload.get("peers", []):
            if url == self.endpoint:
                continue   # don't connect to ourselves
            if url not in self.svc.peers:
                self.svc.add_peer(url)
                if self._discovery:
                    self._discovery.add(url)
                asyncio.create_task(self._connect_outbound(url))

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def _broadcast(
        self,
        msg: P2PMessage,
        exclude: Optional[int] = None,
    ) -> None:
        """Send msg to all connected peers, optionally excluding one by ws id."""
        async with self._peers_lock:
            targets = [
                (k, p) for k, p in self._peers.items()
                if k != exclude and p.is_alive
            ]
        for _, peer in targets:
            asyncio.create_task(peer.send(msg))

    # ── Background maintenance ────────────────────────────────────────────────

    async def _ping_loop(self) -> None:
        """Send PING to all peers every PING_INTERVAL seconds."""
        while True:
            await asyncio.sleep(PING_INTERVAL)
            ts = time.time()
            await self._broadcast(make_ping(ts))

    async def _peer_share_loop(self) -> None:
        """Share our known peer list every PEER_SHARE_INTERVAL seconds."""
        while True:
            await asyncio.sleep(PEER_SHARE_INTERVAL)
            peers = sorted(self.svc.peers)
            if peers:
                await self._broadcast(make_peers_msg(peers))

    # ── Gossip dedup ──────────────────────────────────────────────────────────

    def _already_seen(self, key: str) -> bool:
        return key in self._seen_set

    def _mark_seen(self, key: str) -> None:
        if key in self._seen_set:
            return
        if len(self._seen) >= SEEN_SET_MAX:
            evicted = self._seen.popleft()
            self._seen_set.discard(evicted)
        self._seen.append(key)
        self._seen_set.add(key)

    # ── URL helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_ws_url(base_url: str) -> str:
        """
        Convert a REST base URL to the P2P WebSocket URL.
        Convention: p2p_port = rest_port + 1000
        e.g. http://1.2.3.4:8000  →  ws://1.2.3.4:9000
        """
        import re
        m = re.match(r"https?://([^:/]+)(?::(\d+))?", base_url)
        if not m:
            raise ValueError(f"Cannot parse peer URL: {base_url}")
        host = m.group(1)
        port = int(m.group(2) or "8000")
        return f"ws://{host}:{port + 1000}"
