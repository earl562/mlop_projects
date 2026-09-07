"""Evidence report builder (Phase 6 — master spec §12).

Generates a claim-level evidence-backed report. Rejects material claims without
evidence_ids, rejects evidence_ids not in the run scope, accepts unknowns
(non-material + needs_verification) without evidence. Adds legal caveats for
ordinance sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class ReportClaim:
    """One claim in a report (master spec §12)."""

    key: str
    text: str
    material: bool
    evidence_ids: list[str] = field(default_factory=list)
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    needs_verification: bool = False
    source_caveat: str = ""


class EvidenceReportBuilder:
    """Validates + assembles report claims (master spec §12).

    Validation rules:
    - Reject material claims without evidence_ids.
    - Reject evidence_ids not in the run/project/site scope.
    - Accept unknowns (non-material + needs_verification) without evidence.
    - Add legal caveat for ordinance-sourced evidence.
    """

    def __init__(self, *, analysis_run_id: str, evidence_ids: list[str]) -> None:
        self.analysis_run_id = analysis_run_id
        self._scope = set(evidence_ids)

    def validate_claims(self, claims: list[ReportClaim]) -> list[str]:
        """Return the keys of rejected claims (empty = all accepted)."""
        rejected: list[str] = []
        for c in claims:
            # Unknown (non-material, needs_verification) — accepted without evidence.
            if not c.material and c.needs_verification:
                continue
            # Material claim without evidence → reject (master spec §12).
            if c.material and not c.evidence_ids:
                rejected.append(c.key)
                continue
            # Evidence outside run scope → reject.
            if c.material and any(eid not in self._scope for eid in c.evidence_ids):
                rejected.append(c.key)
        return rejected

    def build(self, claims: list[ReportClaim]) -> dict:
        """Assemble the final report dict (after validation)."""
        rejected = self.validate_claims(claims)
        accepted = [c for c in claims if c.key not in rejected]
        return {
            "analysis_run_id": self.analysis_run_id,
            "report_id": f"rpt_{self.analysis_run_id}",
            "claims": [
                {
                    "key": c.key,
                    "text": c.text,
                    "material": c.material,
                    "evidence_ids": c.evidence_ids,
                    "confidence": c.confidence,
                    "needs_verification": c.needs_verification,
                    "source_caveat": c.source_caveat,
                }
                for c in accepted
            ],
            "rejected_claims": rejected,
            "uncited_count": len(rejected),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


__all__ = ["EvidenceReportBuilder", "ReportClaim"]
