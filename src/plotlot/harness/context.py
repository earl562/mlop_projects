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
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class ContextPacket:
    workspace_id: str
    project_id: str | None
    site_id: str | None
    objective: str
    evidence_ids: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    # Lifecycle tracking for acquisition/development process
    current_phase: str | None = None  # acquisition, entitlement, design, construction, disposition
    phase_gate_criteria: dict[str, Any] = field(default_factory=dict)  # criteria to advance to next phase
    decision_history: list[dict[str, Any]] = field(default_factory=list)  # key decisions with timestamps
    stakeholder_context: dict[str, Any] = field(default_factory=dict)  # who's involved, their requirements
    timeline_milestones: dict[str, Any] = field(default_factory=dict)  # target dates, actual completion
    risk_register: list[dict[str, Any]] = field(default_factory=list)  # identified risks, mitigation status, ownership
    resource_allocation: dict[str, Any] = field(default_factory=dict)  # budget, team, external consultants


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
