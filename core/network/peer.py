"""
PeerConnection — wraps a single WebSocket connection to one remote peer.

Handles:
  - Sending messages with error recovery
  - Tracking peer metadata (node_id, chain state, latency)
  - Disconnect detection
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from core.network.messages import P2PMessage

log = logging.getLogger(__name__)


class PeerConnection:
    """
    Represents a live WebSocket connection to a remote peer.
    Created for both inbound (they connected to us) and outbound (we connected to them).
    """

    def __init__(
        self,
        websocket,            # websockets.WebSocketCommonProtocol
        peer_url: str = "",   # base URL as announced in HANDSHAKE (e.g. "http://1.2.3.4:8000")
        direction: str = "inbound",  # "inbound" | "outbound"
    ) -> None:
        self.ws          = websocket
        self.peer_url    = peer_url
        self.direction   = direction

        # Populated after HANDSHAKE
        self.node_id:      str   = ""
        self.endpoint:     str   = peer_url
        self.p2p_port:     int   = 0
        self.chain_height: int   = 0
        self.tip_hash:     str   = ""
        self.handshake_done:bool = False

        # Stats
        self.connected_at: float = time.time()
        self.last_seen:    float = time.time()
        self.bytes_sent:   int   = 0
        self.bytes_recv:   int   = 0

        self._send_lock = asyncio.Lock()

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send(self, msg: P2PMessage) -> bool:
        """
        Send a message. Returns False if the connection is broken.
        Thread-safe (uses a per-peer lock).
        """
        async with self._send_lock:
            try:
                raw = msg.encode()
                await self.ws.send(raw)
                self.bytes_sent += len(raw)
                return True
            except Exception as e:
                log.debug("Send failed to %s: %s", self.short_id, e)
                return False

    # ── Metadata ──────────────────────────────────────────────────────────────

    def update_from_handshake(self, payload: dict) -> None:
        self.node_id      = payload.get("node_id", "")
        self.endpoint     = payload.get("endpoint", self.peer_url)
        self.p2p_port     = payload.get("p2p_port", 0)
        self.chain_height = payload.get("chain_height", 0)
        self.tip_hash     = payload.get("tip_hash", "")
        self.handshake_done = True
        self.last_seen    = time.time()

    def update_chain_state(self, height: int, tip_hash: str) -> None:
        self.chain_height = height
        self.tip_hash     = tip_hash
        self.last_seen    = time.time()

    def touch(self) -> None:
        self.last_seen = time.time()

    @property
    def short_id(self) -> str:
        if self.node_id:
            return self.node_id[:8] + "…"
        return self.peer_url or f"<{self.direction}>"

    @property
    def is_alive(self) -> bool:
        # websockets >= 12.0: use .state (an enum; OPEN has name "OPEN")
        state = getattr(self.ws, "state", None)
        if state is not None:
            return getattr(state, "name", str(state)) == "OPEN"
        # websockets < 12.0 legacy API
        if hasattr(self.ws, "open"):
            return bool(self.ws.open)
        return not getattr(self.ws, "closed", True)

    @property
    def latency_ms(self) -> float:
        """Rough estimate: time since last_seen (seconds) * 1000."""
        return (time.time() - self.last_seen) * 1000

    def to_dict(self) -> dict:
        return {
            "node_id":      self.node_id,
            "endpoint":     self.endpoint,
            "direction":    self.direction,
            "chain_height": self.chain_height,
            "tip_hash":     self.tip_hash[:8] + "…" if self.tip_hash else "",
            "latency_ms":   round(self.latency_ms, 1),
            "connected_at": self.connected_at,
        }

    def __repr__(self) -> str:
        return f"Peer({self.short_id}, height={self.chain_height}, {self.direction})"
