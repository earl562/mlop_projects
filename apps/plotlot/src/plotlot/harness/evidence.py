"""Evidence recording scaffold for harness runs.

This is intentionally lightweight: it provides a seam for future persistence
without forcing a database migration in the first harness milestone.
"""

from __future__ import annotations

from typing import Any


class EvidenceRecorder:
    """Records evidence references produced during a skill run."""

    def __init__(self) -> None:
        self._last_ids: list[str] = []

    async def record_zoning_report(
        self,
        *,
        workspace_id: str | None,
        project_id: str | None,
        site_id: str | None,
        report: Any,
    ) -> list[str]:
        _ = (workspace_id, project_id, site_id)
        evidence_ids: list[str] = []

        for idx, _source in enumerate(getattr(report, "sources", []) or []):
            evidence_ids.append(f"ev_source_{idx}")

        self._last_ids = evidence_ids
        return evidence_ids

    def last_ids(self) -> list[str]:
        return list(self._last_ids)
