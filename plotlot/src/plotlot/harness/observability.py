from dataclasses import dataclass
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
