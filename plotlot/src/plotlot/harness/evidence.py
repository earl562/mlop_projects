"""Evidence lineage — claim tracking, survival monitoring, audit trail.

Per Image 2 (Obsidian vault): "Every eval data point is the agent equivalent of a training gradient."
Per How we build evals (LangChain): evidence lineage with traceability.
Per OpenAI Harness Engineering: claim survival as primary quality metric.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


@dataclass
class EvidenceClaim:
    claim_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = ""
    source_document: str = ""
    source_section: str = ""
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    survived_review: bool | None = None
    reviewer: str = ""


class EvidenceLedger:
    """Immutable append-only ledger of all agent claims."""

    def __init__(self):
        self._claims: list[EvidenceClaim] = []

    def record(self, claim: EvidenceClaim) -> None:
        self._claims.append(claim)

    def query(self, source_document: str | None = None, source_section: str | None = None, min_confidence: float = 0.0) -> list[EvidenceClaim]:
        results = self._claims
        if source_document:
            results = [c for c in results if source_document.lower() in c.source_document.lower()]
        if source_section:
            results = [c for c in results if source_section.lower() in c.source_section.lower()]
        if min_confidence > 0:
            results = [c for c in results if c.confidence >= min_confidence]
        return results

    def to_dicts(self) -> list[dict[str, Any]]:
        return [{"claim_id": c.claim_id, "text": c.text[:200], "source": c.source_document, "confidence": c.confidence, "survived": c.survived_review} for c in self._claims]

    @property
    def total_claims(self) -> int:
        return len(self._claims)


class ClaimSurvivalTracker:
    """Track which agent claims survive human review."""

    def __init__(self):
        self._reviews: list[dict[str, Any]] = []

    def record_review(self, claim_id: str, survived: bool, reviewer: str = "unknown") -> None:
        self._reviews.append({"claim_id": claim_id, "survived": survived, "reviewer": reviewer, "at": datetime.now(timezone.utc).isoformat()})

    def survival_rate(self) -> float:
        if not self._reviews:
            return 1.0
        survived = sum(1 for r in self._reviews if r["survived"])
        return survived / len(self._reviews)

    def to_summary(self) -> dict[str, Any]:
        return {"total_reviews": len(self._reviews), "survival_rate": round(self.survival_rate(), 3), "reviews": self._reviews[-20:]}


class EvidenceMiddleware(AgentMiddleware):
    """Scan agent output for cited claims and record them."""

    def __init__(self, ledger: EvidenceLedger | None = None):
        self._ledger = ledger or EvidenceLedger()

    @property
    def name(self) -> str:
        return "EvidenceMiddleware"

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    async def after_agent(self, state: AgentState) -> AgentState:
        for msg in state.messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "§" in content or "Section" in content or "ordinance" in content.lower():
                    claim = EvidenceClaim(text=content[:500], source_document="agent_output", confidence=0.9)
                    self._ledger.record(claim)
        state.custom["claims_recorded"] = self._ledger.total_claims
        return state


class AuditTrail:
    """JSON-serializable log of all tool calls with timestamps."""

    def __init__(self):
        self._entries: list[dict[str, Any]] = []

    def log_call(self, tool_name: str, args: dict[str, Any], result_status: str, run_id: str | None = None) -> None:
        self._entries.append({"tool": tool_name, "args": str(args)[:500], "status": result_status, "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat()})

    def export(self) -> str:
        return json.dumps(self._entries, indent=2, default=str)

    def to_dicts(self) -> list[dict[str, Any]]:
        return list(self._entries)

    @property
    def total_entries(self) -> int:
        return len(self._entries)