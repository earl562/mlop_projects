"""Tests for Observability (AC-3.3)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Claim:
    id: str
    claim_key: str
    value: Any
    status: str = "pending"


class ObservabilityTracker:
    def __init__(self):
        self.claims = []

    def track_claim(self, claim: Claim):
        self.claims.append(claim)

    def get_survival_metrics(self) -> dict[str, float]:
        total = len(self.claims)
        if total == 0:
            return {"survival_rate": 0.0, "overwritten_rate": 0.0}
        survived = sum(1 for c in self.claims if c.status == "accepted")
        overwritten = sum(1 for c in self.claims if c.status == "overwritten")
        return {
            "survival_rate": survived / total,
            "overwritten_rate": overwritten / total,
        }


class TestObservability:
    def test_claim_tracked(self):
        tracker = ObservabilityTracker()
        claim = Claim(id="c1", claim_key="max_units", value=8)
        tracker.track_claim(claim)
        assert len(tracker.claims) == 1

    def test_survival_rate_calculated(self):
        tracker = ObservabilityTracker()
        tracker.track_claim(Claim(id="c1", claim_key="max_units", value=8, status="accepted"))
        tracker.track_claim(Claim(id="c2", claim_key="setback", value=25, status="accepted"))
        tracker.track_claim(Claim(id="c3", claim_key="height", value=45, status="overwritten"))
        metrics = tracker.get_survival_metrics()
        assert metrics["survival_rate"] == 2 / 3
        assert metrics["overwritten_rate"] == 1 / 3
