"""
Reliability tracking for QoI participants.

Purpose:
- Provide an anti-gaming signal independent of self-reported OOD scores
- Maintain per-node reliability based on recent consensus behavior
- Feed reliability into quorum election weighting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NodeReliability:
    node_id: str
    score: float = 1.0
    rounds: int = 0
    honest_rounds: int = 0
    byzantine_rounds: int = 0
    challenge_rounds: int = 0
    challenge_penalties: int = 0


class ReliabilityRegistry:
    """In-memory process-global reliability registry."""

    def __init__(self) -> None:
        self._scores: dict[str, NodeReliability] = {}

    def get_score(self, node_id: str) -> float:
        rec = self._scores.get(node_id)
        if rec is None:
            return 1.0
        return rec.score

    def update_from_round(self, round_result: Any, alpha: float = 0.2) -> None:
        """
        Update reliability with EMA after each committed QoI round.

        target:
          honest node   -> higher target from QoI score (up to 1.2)
          byzantine     -> low target (0.2)
        """
        for nr in getattr(round_result, "node_results", []):
            node_id = nr.node_id
            rec = self._scores.get(node_id)
            if rec is None:
                rec = NodeReliability(node_id=node_id)
                self._scores[node_id] = rec

            rec.rounds += 1
            if nr.is_honest:
                rec.honest_rounds += 1
                target = 0.6 + 0.6 * float(max(0.0, min(1.0, nr.qoi_score)))
            else:
                rec.byzantine_rounds += 1
                target = 0.2

            rec.score = (1.0 - alpha) * rec.score + alpha * target
            rec.score = max(0.05, min(1.5, rec.score))

    def update_from_challenge(self, challenge_record: Any, alpha: float = 0.45) -> None:
        """
        Apply stronger anti-gaming updates on challenge rounds.

        Rule of thumb:
        - high knowledge + dishonest outcome => strong penalty
        - high knowledge + honest outcome => reward calibration
        - low knowledge + honest => mild reward (conservative behavior)
        """
        if not getattr(challenge_record, "challenge", False):
            return

        for row in getattr(challenge_record, "results", []):
            node_id = row.node_id
            rec = self._scores.get(node_id)
            if rec is None:
                rec = NodeReliability(node_id=node_id)
                self._scores[node_id] = rec

            rec.challenge_rounds += 1

            k = float(row.knowledge_score if row.knowledge_score is not None else 0.5)
            if row.is_honest:
                # reward honesty; stronger if node claimed high familiarity
                target = 0.65 + 0.55 * k
            else:
                # dishonest with high claimed knowledge is heavily penalized
                target = 0.25 - 0.2 * k
                if k >= 0.7:
                    rec.challenge_penalties += 1

            rec.score = (1.0 - alpha) * rec.score + alpha * target
            rec.score = max(0.01, min(1.5, rec.score))

    def summary(self, node_id: str) -> dict:
        rec = self._scores.get(node_id)
        if rec is None:
            return {
                "node_id": node_id,
                "score": 1.0,
                "rounds": 0,
                "honest_rounds": 0,
                "byzantine_rounds": 0,
                "challenge_rounds": 0,
                "challenge_penalties": 0,
            }
        return {
            "node_id": rec.node_id,
            "score": rec.score,
            "rounds": rec.rounds,
            "honest_rounds": rec.honest_rounds,
            "byzantine_rounds": rec.byzantine_rounds,
            "challenge_rounds": rec.challenge_rounds,
            "challenge_penalties": rec.challenge_penalties,
        }


_global_reliability_registry = ReliabilityRegistry()


def get_reliability_registry() -> ReliabilityRegistry:
    return _global_reliability_registry
