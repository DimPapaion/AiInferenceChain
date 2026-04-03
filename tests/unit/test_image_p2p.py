"""
Unit tests for the decentralised P2P image fetch protocol.

Tests cover:
- `_on_image_request` : peer asks for image we have / don't have
- `_on_image_response`: we receive image bytes — integrity check, store, wake event
- `fetch_image`       : fast-path (local hit), no-peers path, timeout path
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.network.messages import MsgType, make_image_request, make_image_response
from core.network.p2p_server import P2PServer
from core.serving.image_store import ImageStore


# ── Helpers ───────────────────────────────────────────────────────────────────

IMAGE_BYTES = b"\x00\x01\x02" * 100
IMAGE_HASH  = hashlib.sha256(IMAGE_BYTES).hexdigest()


def _make_server(tmp_dir: str) -> P2PServer:
    """Create a minimal P2PServer with an attached ImageStore."""
    svc = MagicMock()
    svc.chain.height = 0
    svc.chain.tip.hash = "genesis"
    server = P2PServer(
        node_service = svc,
        node_id      = "test_node",
        endpoint     = "http://127.0.0.1:9000",
        p2p_port     = 9000,
    )
    store = ImageStore(base_dir=tmp_dir)
    server.attach_image_store(store)
    return server


def _make_peer() -> MagicMock:
    peer       = MagicMock()
    peer.send  = AsyncMock()
    peer.short_id = "peer_abc"
    return peer


# ── _on_image_request ─────────────────────────────────────────────────────────

class TestOnImageRequest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = _make_server(self.tmp)
        self.peer   = _make_peer()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_serves_image_when_held_locally(self):
        """If we have the image, we send IMAGE_RESPONSE back to the requester."""
        self.server._image_store.put(IMAGE_BYTES)

        self._run(self.server._on_image_request(
            self.peer, {"image_hash": IMAGE_HASH}
        ))

        self.peer.send.assert_called_once()
        sent: dict = self.peer.send.call_args[0][0].payload
        assert sent["image_hash"] == IMAGE_HASH
        assert bytes.fromhex(sent["data_hex"]) == IMAGE_BYTES

    def test_silent_when_image_not_held(self):
        """If we don't have the image, we don't respond at all."""
        self._run(self.server._on_image_request(
            self.peer, {"image_hash": IMAGE_HASH}
        ))
        self.peer.send.assert_not_called()

    def test_silent_when_no_image_store(self):
        self.server._image_store = None
        self._run(self.server._on_image_request(
            self.peer, {"image_hash": IMAGE_HASH}
        ))
        self.peer.send.assert_not_called()

    def test_ignores_empty_hash(self):
        self.server._image_store.put(IMAGE_BYTES)
        self._run(self.server._on_image_request(self.peer, {"image_hash": ""}))
        self.peer.send.assert_not_called()


# ── _on_image_response ────────────────────────────────────────────────────────

class TestOnImageResponse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = _make_server(self.tmp)
        self.peer   = _make_peer()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_stores_image_on_valid_response(self):
        self._run(self.server._on_image_response(self.peer, {
            "image_hash": IMAGE_HASH,
            "data_hex":   IMAGE_BYTES.hex(),
        }))
        assert self.server._image_store.has(IMAGE_HASH)
        assert self.server._image_store.get(IMAGE_HASH) == IMAGE_BYTES

    def test_sets_pending_event(self):
        evt = asyncio.Event()
        self.server._pending_image_fetches[IMAGE_HASH] = evt

        self._run(self.server._on_image_response(self.peer, {
            "image_hash": IMAGE_HASH,
            "data_hex":   IMAGE_BYTES.hex(),
        }))

        assert evt.is_set()

    def test_rejects_corrupted_bytes(self):
        """If hash doesn't match the payload, nothing is stored."""
        wrong_hash = "0" * 64
        self._run(self.server._on_image_response(self.peer, {
            "image_hash": wrong_hash,
            "data_hex":   IMAGE_BYTES.hex(),
        }))
        assert not self.server._image_store.has(wrong_hash)

    def test_rejects_invalid_hex(self):
        self._run(self.server._on_image_response(self.peer, {
            "image_hash": IMAGE_HASH,
            "data_hex":   "notvalidhex!!",
        }))
        assert not self.server._image_store.has(IMAGE_HASH)

    def test_ignores_missing_fields(self):
        # Should not raise even with empty payload
        self._run(self.server._on_image_response(self.peer, {}))

    def test_does_not_crash_without_image_store(self):
        self.server._image_store = None
        evt = asyncio.Event()
        self.server._pending_image_fetches[IMAGE_HASH] = evt
        self._run(self.server._on_image_response(self.peer, {
            "image_hash": IMAGE_HASH,
            "data_hex":   IMAGE_BYTES.hex(),
        }))
        # Event is still set — waiting fetch gets unblocked
        assert evt.is_set()


# ── fetch_image ───────────────────────────────────────────────────────────────

class TestFetchImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = _make_server(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_local_hit_returns_immediately(self):
        """If image is already in the local store, return it without P2P."""
        self.server._image_store.put(IMAGE_BYTES)
        result = self._run(self.server.fetch_image(IMAGE_HASH))
        assert result == IMAGE_BYTES

    def test_no_peers_returns_none(self):
        """With no connected peers there is nobody to ask."""
        # _peers is empty by default
        result = self._run(self.server.fetch_image(IMAGE_HASH))
        assert result is None

    def test_timeout_returns_none(self):
        """If peers don't respond within timeout, return None."""
        # Add a fake peer so we pass the no-peers guard
        fake_peer = MagicMock()
        fake_peer.send = AsyncMock()
        self.server._peers = {"peer1": fake_peer}
        self.server._broadcast = AsyncMock()

        result = self._run(self.server.fetch_image(IMAGE_HASH, timeout=0.05))
        assert result is None
        # Pending entry must be cleaned up
        assert IMAGE_HASH not in self.server._pending_image_fetches

    def test_successful_p2p_fetch(self):
        """
        Simulate a peer responding with IMAGE_RESPONSE while we wait.
        The response handler stores the image and sets the event;
        fetch_image should return the bytes.
        """
        fake_peer = MagicMock()
        fake_peer.send = AsyncMock()
        self.server._peers = {"peer1": fake_peer}
        self.server._broadcast = AsyncMock()

        async def _simulate_peer_response():
            # Give fetch_image time to register the event and broadcast
            await asyncio.sleep(0.02)
            await self.server._on_image_response(fake_peer, {
                "image_hash": IMAGE_HASH,
                "data_hex":   IMAGE_BYTES.hex(),
            })

        async def _run_both():
            result, _ = await asyncio.gather(
                self.server.fetch_image(IMAGE_HASH, timeout=2.0),
                _simulate_peer_response(),
            )
            return result

        result = asyncio.run(_run_both())
        assert result == IMAGE_BYTES


# ── make_image_request / make_image_response message factories ────────────────

class TestMessageFactories(unittest.TestCase):
    def test_make_image_request(self):
        msg = make_image_request(IMAGE_HASH)
        assert msg.type == MsgType.IMAGE_REQUEST
        assert msg.payload["image_hash"] == IMAGE_HASH

    def test_make_image_response(self):
        msg = make_image_response(IMAGE_HASH, IMAGE_BYTES.hex())
        assert msg.type == MsgType.IMAGE_RESPONSE
        assert msg.payload["image_hash"] == IMAGE_HASH
        assert msg.payload["data_hex"]   == IMAGE_BYTES.hex()
