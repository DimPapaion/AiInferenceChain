"""
WebSocket handler for real-time dashboard streaming.

Streams:
- Consensus round updates
- Validator activity
- Model validation progress

Wire to the event bus at startup via:
    get_stream_manager().wire_to_event_bus()
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from fastapi import WebSocket
from core.events import ConsensusEvent, EventType, get_global_bus
from core.utils.logger import get_logger

_NOW = lambda: datetime.now(timezone.utc).isoformat()


class ConsensusStreamManager:
    """
    Manages WebSocket connections for real-time consensus updates.

    Channels:
    - consensus_rounds: QoI and PoS block commit events
    - validators: Validator activity
    - models: Model validation progress
    """

    def __init__(self):
        self.logger = get_logger("consensus_stream")
        self.connections: Dict[str, Set[WebSocket]] = {
            "consensus_rounds": set(),
            "validators": set(),
            "models": set(),
        }
        self._wired = False
        self.logger.info("ConsensusStreamManager initialized")

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        self.connections.setdefault(channel, set()).add(websocket)
        self.logger.debug(
            "Client connected to stream",
            context={"channel": channel, "total_clients": len(self.connections[channel])},
        )

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        if channel in self.connections:
            self.connections[channel].discard(websocket)
            self.logger.debug(
                "Client disconnected from stream",
                context={"channel": channel, "remaining_clients": len(self.connections[channel])},
            )

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def broadcast(self, channel: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.connections.get(channel, set()):
            try:
                await ws.send_json(message)
            except Exception as e:
                self.logger.debug(
                    "Failed to send to client",
                    context={"error": str(e), "channel": channel},
                )
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def broadcast_consensus_round(
        self,
        round_number: int,
        phase: str,
        status: str,
        participants: int,
    ) -> None:
        await self.broadcast("consensus_rounds", {
            "type":         "consensus_round",
            "timestamp":    _NOW(),
            "round":        round_number,
            "phase":        phase,
            "status":       status,
            "participants": participants,
        })

    async def broadcast_validator_activity(
        self,
        validator_id: str,
        action: str,
        details: dict | None = None,
    ) -> None:
        await self.broadcast("validators", {
            "type":         "validator_activity",
            "timestamp":    _NOW(),
            "validator_id": validator_id,
            "action":       action,
            "details":      details or {},
        })

    async def broadcast_model_validation(
        self,
        model_id: str,
        status: str,
        progress: float = 0.0,
        message: str = "",
    ) -> None:
        await self.broadcast("models", {
            "type":      "model_validation",
            "timestamp": _NOW(),
            "model_id":  model_id,
            "status":    status,
            "progress":  progress,
            "message":   message,
        })

    # ── Event bus wiring ──────────────────────────────────────────────────────

    def wire_to_event_bus(self, bus=None) -> None:
        """
        Subscribe to consensus events on the event bus so the WebSocket stream
        receives live data without being polled.

        Safe to call multiple times — skips if already wired.
        """
        if self._wired:
            return
        bus = bus or get_global_bus()

        def _schedule(coro):
            """Bridge: fire-and-forget async broadcast from a sync callback."""
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(coro)
                else:
                    loop.run_until_complete(coro)
            except RuntimeError:
                pass  # no event loop (e.g. test teardown) — silently drop

        def _on_qoi_committed(event: ConsensusEvent) -> None:
            data = event.data
            _schedule(self.broadcast_consensus_round(
                round_number = data.get("view", 0),
                phase        = "commit",
                status       = "committed",
                participants = data.get("participants", 0),
            ))

        def _on_pos_committed(event: ConsensusEvent) -> None:
            data = event.data
            _schedule(self.broadcast_consensus_round(
                round_number = data.get("height", 0),
                phase        = "pos",
                status       = "committed",
                participants = data.get("participants", 0),
            ))

        bus.subscribe(EventType.QOI_COMMITTED, _on_qoi_committed)
        bus.subscribe(EventType.POS_COMMITTED, _on_pos_committed)

        self._wired = True
        self.logger.info("ConsensusStreamManager wired to event bus")

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "consensus_rounds_clients": len(self.connections.get("consensus_rounds", set())),
            "validators_clients":       len(self.connections.get("validators", set())),
            "models_clients":           len(self.connections.get("models", set())),
            "total_clients":            sum(len(v) for v in self.connections.values()),
        }


# Global instance
_stream_manager: Optional[ConsensusStreamManager] = None


def get_stream_manager() -> ConsensusStreamManager:
    """Get or create global stream manager."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = ConsensusStreamManager()
    return _stream_manager
