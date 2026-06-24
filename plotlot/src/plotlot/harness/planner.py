from __future__ import annotations

from plotlot.harness.context import ContextPacket
from plotlot.harness.planner_rules import build_assignments, build_escalations
from plotlot.harness.planner_types import HarnessPlan


class HarnessPlanner:
    def plan(self, packet: ContextPacket) -> HarnessPlan:
        escalations = build_escalations(packet)
        return HarnessPlan(
            objective=packet.objective,
            evidence_ids=packet.evidence_ids,
            assignments=build_assignments(packet, escalations),
            escalations=escalations,
            ready_for_synthesis=not escalations,
        )
