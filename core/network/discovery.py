"""
Peer Discovery for InferenceChain.

Three mechanisms (in order of precedence):
  1. CLI  --peer flags (highest priority — explicit user config)
  2. Seed file  data/peers.txt  (one URL per line, persisted across restarts)
  3. Hardcoded bootstrap seeds (fallback for fresh nodes)

The discovery module:
  - Loads known peers at startup
  - Saves newly discovered peers to the seed file
  - Removes dead peers that fail to connect after MAX_FAILURES attempts
  - Provides seed_peers() for the P2PServer to call on startup
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Hardcoded bootstrap seeds ─────────────────────────────────────────────────
# These are the well-known entry points for the InferenceChain network.
# A fresh node with no seed file tries these first.
# (Empty for now — will be populated when public testnet is deployed.)
HARDCODED_SEEDS: list[str] = [
    # "http://seed1.inferencechain.net:8000",
    # "http://seed2.inferencechain.net:8000",
]

DEFAULT_SEED_FILE = Path("data") / "peers.txt"
MAX_FAILURES      = 5   # remove a peer after this many consecutive failures


class PeerDiscovery:
    """
    Manages the known-peers list, with file persistence.
    """

    def __init__(
        self,
        seed_file:   Path | str = DEFAULT_SEED_FILE,
        extra_peers: list[str]  | None = None,
    ) -> None:
        self.seed_file = Path(seed_file)
        self._peers:    dict[str, int] = {}   # url → consecutive failure count
        self._load()

        # Add hardcoded seeds and CLI peers
        for url in HARDCODED_SEEDS + (extra_peers or []):
            self.add(url)

    # ── Public interface ──────────────────────────────────────────────────────

    def add(self, url: str) -> None:
        """Register a peer URL. Idempotent."""
        url = url.rstrip("/")
        if url and url not in self._peers:
            self._peers[url] = 0
            self._save()

    def remove(self, url: str) -> None:
        url = url.rstrip("/")
        self._peers.pop(url, None)
        self._save()

    def mark_failure(self, url: str) -> None:
        """Record a connection failure. Remove after MAX_FAILURES."""
        url = url.rstrip("/")
        if url in self._peers:
            self._peers[url] += 1
            if self._peers[url] >= MAX_FAILURES:
                log.info("Dropping unresponsive peer %s after %d failures", url, MAX_FAILURES)
                self.remove(url)

    def mark_success(self, url: str) -> None:
        """Reset failure count on successful contact."""
        url = url.rstrip("/")
        if url in self._peers:
            self._peers[url] = 0

    def all_peers(self) -> list[str]:
        return list(self._peers.keys())

    def seed_peers(self) -> list[str]:
        """Return all known peers for initial P2P connection."""
        return self.all_peers()

    def __len__(self) -> int:
        return len(self._peers)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.seed_file.exists():
            return
        try:
            for line in self.seed_file.read_text().splitlines():
                url = line.strip()
                if url and not url.startswith("#"):
                    self._peers[url] = 0
            log.info("Loaded %d peers from %s", len(self._peers), self.seed_file)
        except Exception as e:
            log.warning("Could not load seed file %s: %s", self.seed_file, e)

    def _save(self) -> None:
        try:
            self.seed_file.parent.mkdir(parents=True, exist_ok=True)
            lines = ["# InferenceChain known peers — auto-updated"]
            lines += sorted(self._peers.keys())
            self.seed_file.write_text("\n".join(lines) + "\n")
        except Exception as e:
            log.warning("Could not save seed file %s: %s", self.seed_file, e)
