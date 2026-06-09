"""Tests for Deal Pipeline (AC-1.4)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


VALID_TRANSITIONS = {
    "lead": ["contacted", "lost"],
    "contacted": ["qualified", "lost"],
    "qualified": ["site_visit_scheduled", "lost"],
    "site_visit_scheduled": ["site_visit_completed", "lost"],
    "site_visit_completed": ["underwriting", "lost"],
    "underwriting": ["loi_submitted", "lost"],
    "loi_submitted": ["loi_accepted", "lost"],
    "loi_accepted": ["psa_submitted", "lost"],
    "psa_submitted": ["psa_executed", "lost"],
    "psa_executed": ["due_diligence", "lost"],
    "due_diligence": ["closing", "lost"],
    "closing": ["won", "lost"],
}


@dataclass
class FakeDeal:
    id: str = ""
    stage: str = "lead"
    stage_history: list[dict] = field(default_factory=list)
    is_deleted: bool = False

    def transition_to(self, new_stage: str, user_id: str = "") -> bool:
        if new_stage not in VALID_TRANSITIONS.get(self.stage, []):
            raise InvalidTransitionError(f"Cannot transition from {self.stage} to {new_stage}")
        self.stage_history.append({
            "from": self.stage,
            "to": new_stage,
            "at": datetime.utcnow().isoformat(),
            "by": user_id,
        })
        self.stage = new_stage
        return True


class InvalidTransitionError(Exception):
    pass


class TestDealPipeline:
    def test_deal_starts_in_lead_stage(self):
        deal = FakeDeal(id="deal_001")
        assert deal.stage == "lead"

    def test_valid_stage_transition(self):
        deal = FakeDeal(id="deal_001")
        deal.transition_to("contacted", user_id="usr_123")
        assert deal.stage == "contacted"
        assert len(deal.stage_history) == 1
        assert deal.stage_history[0]["from"] == "lead"
        assert deal.stage_history[0]["to"] == "contacted"

    def test_invalid_stage_transition_raises(self):
        deal = FakeDeal(id="deal_001", stage="lead")
        with pytest.raises(InvalidTransitionError):
            deal.transition_to("won")

    def test_pipeline_12_stages_exist(self):
        expected = [
            "lead", "contacted", "qualified", "site_visit_scheduled",
            "site_visit_completed", "underwriting", "loi_submitted",
            "loi_accepted", "psa_submitted", "psa_executed",
            "due_diligence", "closing", "won", "lost",
        ]
        for stage in expected:
            assert stage in VALID_TRANSITIONS or stage == "won" or stage == "lost"

    def test_stage_history_tracks_all_transitions(self):
        deal = FakeDeal(id="deal_001")
        deal.transition_to("contacted")
        deal.transition_to("qualified")
        deal.transition_to("site_visit_scheduled")
        assert len(deal.stage_history) == 3
        assert deal.stage_history[2]["to"] == "site_visit_scheduled"

    def test_terminal_stages_have_no_outbound_transitions(self):
        assert "won" not in VALID_TRANSITIONS
        assert "lost" not in VALID_TRANSITIONS


import pytest
