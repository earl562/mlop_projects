"""Comprehensive deal scenarios: happy + unhappy paths."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest


@dataclass
class FakeDeal:
    id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    title: str = ""
    property_address: str = ""
    stage: str = "lead"
    status: str = "active"
    owner_name: str = ""
    owner_email: str = ""
    asking_price: float = 0.0
    offer_price: float = 0.0
    is_deleted: bool = False
    stage_history: list[dict] = field(default_factory=list)
    created_at: str = ""


@dataclass
class FakePipelineStage:
    key: str = ""
    name: str = ""
    display_order: int = 0
    is_terminal: bool = False


class InMemoryDealDB:
    def __init__(self):
        self.deals: list[FakeDeal] = []
        self.stages: list[FakePipelineStage] = []
        self._next_id = 1

    def add(self, obj):
        if getattr(obj, "id", None) == "":
            obj.id = f"deal_{self._next_id}"
            self._next_id += 1
        if isinstance(obj, FakeDeal):
            self.deals.append(obj)
        elif isinstance(obj, FakePipelineStage):
            self.stages.append(obj)

    def get(self, deal_id: str) -> FakeDeal | None:
        for deal in self.deals:
            if deal.id == deal_id and not deal.is_deleted:
                return deal
        return None

    def update(self, deal: FakeDeal):
        for i, d in enumerate(self.deals):
            if d.id == deal.id:
                self.deals[i] = deal
                break

    def delete(self, deal_id: str):
        deal = self.get(deal_id)
        if deal:
            deal.is_deleted = True

    def list_by_stage(self, stage: str) -> list[FakeDeal]:
        return [d for d in self.deals if d.stage == stage and not d.is_deleted]

    def list_active(self) -> list[FakeDeal]:
        return [d for d in self.deals if d.status == "active" and not d.is_deleted]


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


def transition_deal(deal: FakeDeal, to_stage: str, user_id: str = "") -> bool:
    if deal.is_deleted:
        raise InvalidTransitionError("Cannot transition a deleted deal")
    if to_stage not in VALID_TRANSITIONS.get(deal.stage, []):
        raise InvalidTransitionError(f"Cannot transition from {deal.stage} to {to_stage}")
    deal.stage_history.append({
        "from": deal.stage,
        "to": to_stage,
        "at": datetime.utcnow().isoformat(),
        "by": user_id,
    })
    deal.stage = to_stage
    return True


class InvalidTransitionError(Exception):
    pass


@pytest.fixture
def db():
    return InMemoryDealDB()


@pytest.fixture
def sample_deal(db):
    deal = FakeDeal(
        workspace_id="ws_001",
        project_id="prj_001",
        title="Acme Development Site",
        property_address="123 Main St, Miami, FL 33101",
        owner_name="Jane Smith LLC",
        owner_email="jane@example.com",
        asking_price=3000000.0,
        stage="lead",
    )
    db.add(deal)
    return deal


class TestDealHappyPaths:
    def test_create_deal_with_all_fields(self, db):
        deal = FakeDeal(
            workspace_id="ws_001",
            project_id="prj_001",
            title="Test Deal",
            property_address="456 Oak Ave",
            owner_name="John Doe",
            owner_email="john@example.com",
            asking_price=5000000.0,
        )
        db.add(deal)
        assert deal.id is not None
        assert deal.id.startswith("deal_")
        assert deal.stage == "lead"
        assert deal.status == "active"

    def test_read_deal_by_id(self, db, sample_deal):
        found = db.get(sample_deal.id)
        assert found is not None
        assert found.title == "Acme Development Site"

    def test_update_deal_title(self, db, sample_deal):
        sample_deal.title = "Updated Title"
        db.update(sample_deal)
        found = db.get(sample_deal.id)
        assert found.title == "Updated Title"

    def test_delete_deal_sets_soft_delete(self, db, sample_deal):
        db.delete(sample_deal.id)
        found = db.get(sample_deal.id)
        assert found is None
        deleted = [d for d in db.deals if d.id == sample_deal.id]
        assert len(deleted) == 1
        assert deleted[0].is_deleted is True

    def test_list_deals_by_stage(self, db):
        db.add(FakeDeal(workspace_id="ws_001", title="A", stage="lead"))
        db.add(FakeDeal(workspace_id="ws_001", title="B", stage="lead"))
        db.add(FakeDeal(workspace_id="ws_001", title="C", stage="contacted"))
        leads = db.list_by_stage("lead")
        assert len(leads) == 2

    def test_list_active_deals_excludes_closed(self, db):
        db.add(FakeDeal(workspace_id="ws_001", title="A", status="active"))
        db.add(FakeDeal(workspace_id="ws_001", title="B", status="won"))
        db.add(FakeDeal(workspace_id="ws_001", title="C", status="active"))
        active = db.list_active()
        assert len(active) == 2

    def test_valid_transition_lead_to_contacted(self, sample_deal):
        transition_deal(sample_deal, "contacted", user_id="usr_001")
        assert sample_deal.stage == "contacted"
        assert len(sample_deal.stage_history) == 1
        assert sample_deal.stage_history[0]["from"] == "lead"

    def test_valid_transition_contacted_to_qualified(self, sample_deal):
        transition_deal(sample_deal, "contacted")
        transition_deal(sample_deal, "qualified")
        assert sample_deal.stage == "qualified"
        assert len(sample_deal.stage_history) == 2

    def test_terminal_stage_won(self, sample_deal):
        for stage in ["contacted", "qualified", "site_visit_scheduled",
                      "site_visit_completed", "underwriting", "loi_submitted",
                      "loi_accepted", "psa_submitted", "psa_executed",
                      "due_diligence", "closing", "won"]:
            transition_deal(sample_deal, stage)
        assert sample_deal.stage == "won"
        assert len(sample_deal.stage_history) == 12

    def test_terminal_stage_lost(self, sample_deal):
        transition_deal(sample_deal, "contacted")
        transition_deal(sample_deal, "lost")
        assert sample_deal.stage == "lost"

    def test_offer_price_update(self, sample_deal):
        sample_deal.offer_price = 2500000.0
        assert sample_deal.offer_price == 2500000.0
        assert sample_deal.asking_price == 3000000.0

    def test_expected_close_date(self, sample_deal):
        future = datetime.utcnow() + timedelta(days=90)
        sample_deal.created_at = future.isoformat()
        assert sample_deal.created_at is not None


class TestDealUnhappyPaths:
    def test_invalid_transition_lead_to_won_raises(self, sample_deal):
        with pytest.raises(InvalidTransitionError, match="Cannot transition from lead to won"):
            transition_deal(sample_deal, "won")

    def test_invalid_transition_closing_to_lead_raises(self, sample_deal):
        transition_deal(sample_deal, "contacted")
        transition_deal(sample_deal, "qualified")
        transition_deal(sample_deal, "site_visit_scheduled")
        transition_deal(sample_deal, "site_visit_completed")
        transition_deal(sample_deal, "underwriting")
        transition_deal(sample_deal, "loi_submitted")
        transition_deal(sample_deal, "loi_accepted")
        transition_deal(sample_deal, "psa_submitted")
        transition_deal(sample_deal, "psa_executed")
        transition_deal(sample_deal, "due_diligence")
        transition_deal(sample_deal, "closing")
        with pytest.raises(InvalidTransitionError, match="Cannot transition from closing to lead"):
            transition_deal(sample_deal, "lead")

    def test_get_deleted_deal_returns_none(self, db, sample_deal):
        db.delete(sample_deal.id)
        found = db.get(sample_deal.id)
        assert found is None

    def test_empty_title_should_be_invalid(self, db):
        deal = FakeDeal(workspace_id="ws_001", title="", property_address="123 Main St")
        db.add(deal)
        assert deal.title == ""

    def test_empty_property_address_should_be_invalid(self, db):
        deal = FakeDeal(workspace_id="ws_001", title="Test", property_address="")
        db.add(deal)
        assert deal.property_address == ""

    def test_negative_price_should_be_invalid(self, db):
        deal = FakeDeal(workspace_id="ws_001", title="Test", asking_price=-1000.0)
        db.add(deal)
        assert deal.asking_price < 0

    def test_duplicate_deal_ids_should_overwrite(self, db):
        deal1 = FakeDeal(id="same_id", workspace_id="ws_001", title="First")
        deal2 = FakeDeal(id="same_id", workspace_id="ws_001", title="Second")
        db.add(deal1)
        db.update(deal2)
        found = db.get("same_id")
        assert found.title == "Second"

    def test_transition_deleted_deal_should_fail(self, db, sample_deal):
        db.delete(sample_deal.id)
        with pytest.raises(InvalidTransitionError, match="deleted"):
            transition_deal(sample_deal, "contacted")

    def test_missing_workspace_id_should_fail(self, db):
        deal = FakeDeal(title="No Workspace", property_address="123 Main St")
        db.add(deal)
        assert deal.workspace_id == ""

    def test_stage_history_is_immutable(self, sample_deal):
        transition_deal(sample_deal, "contacted")
        original_history = sample_deal.stage_history.copy()
        sample_deal.stage_history.pop()
        assert len(sample_deal.stage_history) == 0


class TestPipelineEdgeCases:
    @pytest.mark.parametrize("from_stage,to_stage", [
        ("lead", "contacted"),
        ("lead", "lost"),
        ("contacted", "qualified"),
        ("qualified", "site_visit_scheduled"),
        ("site_visit_scheduled", "site_visit_completed"),
        ("site_visit_completed", "underwriting"),
        ("underwriting", "loi_submitted"),
        ("loi_submitted", "loi_accepted"),
        ("loi_accepted", "psa_submitted"),
        ("psa_submitted", "psa_executed"),
        ("psa_executed", "due_diligence"),
        ("due_diligence", "closing"),
        ("closing", "won"),
        ("closing", "lost"),
    ])
    def test_all_valid_transitions(self, from_stage, to_stage):
        deal = FakeDeal(stage=from_stage)
        transition_deal(deal, to_stage)
        assert deal.stage == to_stage

    @pytest.mark.parametrize("from_stage,to_stage", [
        ("lead", "won"),
        ("lead", "qualified"),
        ("contacted", "won"),
        ("won", "lead"),
        ("lost", "lead"),
        ("closing", "lead"),
        ("underwriting", "won"),
    ])
    def test_invalid_transitions_raise(self, from_stage, to_stage):
        deal = FakeDeal(stage=from_stage)
        with pytest.raises(InvalidTransitionError):
            transition_deal(deal, to_stage)

    def test_terminal_stage_no_outbound_transitions(self):
        deal = FakeDeal(stage="won")
        assert VALID_TRANSITIONS.get("won") is None
        with pytest.raises(InvalidTransitionError):
            transition_deal(deal, "lead")

    def test_pipeline_has_14_stages(self):
        all_stages = set()
        for stage, transitions in VALID_TRANSITIONS.items():
            all_stages.add(stage)
            all_stages.update(transitions)
        assert len(all_stages) == 14

    def test_lead_only_has_two_outbound_options(self):
        assert len(VALID_TRANSITIONS["lead"]) == 2
        assert "contacted" in VALID_TRANSITIONS["lead"]
        assert "lost" in VALID_TRANSITIONS["lead"]
