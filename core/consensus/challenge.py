"""
Deterministic hidden challenge rounds for anti-gaming reliability.

This module adds challenge instrumentation on top of normal QoI rounds.
A subset of rounds is deterministically marked as challenge rounds, and the
result is recorded for reliability updates and operator visibility.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Any


DEFAULT_CHALLENGE_RATE = 0.15


@dataclass
class NodeChallengeResult:
    node_id: str
    is_honest: bool
    qoi_score: float
    ood_score: float | None = None
    knowledge_score: float | None = None


@dataclass
class RoundChallengeRecord:
    timestamp: int
    request_id: str
    image_hash: str
    block_hash: str
    challenge: bool
    challenge_seed: str
    quorum_size: int
    results: list[NodeChallengeResult]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "image_hash": self.image_hash,
            "block_hash": self.block_hash,
            "challenge": self.challenge,
            "challenge_seed": self.challenge_seed,
            "quorum_size": self.quorum_size,
            "results": [asdict(r) for r in self.results],
        }


class ChallengeRegistry:
    def __init__(self, keep_last: int = 500) -> None:
        self.keep_last = keep_last
        self._items: list[RoundChallengeRecord] = []

    def add(self, record: RoundChallengeRecord) -> None:
        self._items.append(record)
        if len(self._items) > self.keep_last:
            self._items = self._items[-self.keep_last :]

    def recent(self, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._items[-limit:]][::-1]


_global_challenge_registry = ChallengeRegistry()


def get_challenge_registry() -> ChallengeRegistry:
    return _global_challenge_registry


def challenge_seed(request_id: str, block_hash: str) -> str:
    raw = f"{request_id}|{block_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_challenge_round(request_id: str, block_hash: str, rate: float = DEFAULT_CHALLENGE_RATE) -> tuple[bool, str]:
    """Deterministically decide whether this round is challenge-enabled."""
    seed = challenge_seed(request_id, block_hash)
    # map first 8 hex chars to [0,1)
    value = int(seed[:8], 16) / 0xFFFFFFFF
    return value < rate, seed


def _knowledge_from_ood_scores(ood_scores: dict[str, float]) -> dict[str, float]:
    finite = [s for s in ood_scores.values() if s < float("inf")]
    if not finite:
        return {nid: 0.05 for nid in ood_scores}

    mu = sum(finite) / len(finite)
    var = sum((s - mu) ** 2 for s in finite) / max(1, len(finite))
    std = var ** 0.5 or 1.0

    out: dict[str, float] = {}
    for nid, s in ood_scores.items():
        if s == float("inf"):
            out[nid] = 0.05
            continue
        z = -(s - mu) / std
        out[nid] = 1.0 / (1.0 + (2.718281828 ** (-z)))
    return out


def build_round_challenge_record(
    request_id: str,
    image_hash: str,
    block_hash: str,
    challenge: bool,
    challenge_seed_hex: str,
    round_result: Any,
    ood_scores: dict[str, float] | None,
) -> RoundChallengeRecord:
    ood_scores = ood_scores or {}
    k_scores = _knowledge_from_ood_scores(ood_scores)

    rows: list[NodeChallengeResult] = []
    for nr in getattr(round_result, "node_results", []):
        rows.append(
            NodeChallengeResult(
                node_id=nr.node_id,
                is_honest=bool(nr.is_honest),
                qoi_score=float(nr.qoi_score),
                ood_score=(None if nr.node_id not in ood_scores else float(ood_scores[nr.node_id])),
                knowledge_score=(None if nr.node_id not in k_scores else float(k_scores[nr.node_id])),
            )
        )

    return RoundChallengeRecord(
        timestamp=int(time.time()),
        request_id=request_id,
        image_hash=image_hash,
        block_hash=block_hash,
        challenge=challenge,
        challenge_seed=challenge_seed_hex,
        quorum_size=len(rows),
        results=rows,
    )
