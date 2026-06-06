"""Context broker for the harness runtime.

This first slice provides a bounded packet of:

- the user objective
- site selectors (workspace/project/site)
- any existing evidence IDs
- lifecycle tracking for acquisition/development process

Later iterations can add ranking, token budgeting, and report/document state.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextPacket:
    workspace_id: str
    project_id: str | None
    site_id: str | None
    objective: str
    evidence_ids: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


class ContextBroker:
    def build_packet(
        self,
        *,
        workspace_id: str,
        objective: str,
        project_id: str | None = None,
        site_id: str | None = None,
        evidence_ids: list[str] | None = None,
    ) -> ContextPacket:
        return ContextPacket(
            workspace_id=workspace_id,
            project_id=project_id,
            site_id=site_id,
            objective=objective,
            evidence_ids=list(evidence_ids or []),
        )
