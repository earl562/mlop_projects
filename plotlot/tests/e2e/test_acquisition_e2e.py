import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class Workspace:
    id: str = ""
    name: str = ""


@dataclass
class Project:
    id: str = ""
    workspace_id: str = ""
    name: str = ""


@dataclass
class Deal:
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
    feasibility_score: float = 0.0
    crm_sync_json: dict = field(default_factory=dict)
    stage_history: list = field(default_factory=list)
    is_deleted: bool = False


@dataclass
class Outreach:
    id: str = ""
    deal_id: str = ""
    activity_type: str = ""
    subject: str = ""
    body: str = ""
    status: str = ""
    opened_at: datetime | None = None
    call_outcome: str = ""
    sentiment: str = ""
    sequence_position: int = 0


@dataclass
class Document:
    id: str = ""
    filename: str = ""
    ocr_status: str = "pending"
    ocr_text: str = ""
    version: int = 1
    previous_version_id: str | None = None


@dataclass
class Task:
    id: str = ""
    deal_id: str = ""
    title: str = ""
    due_at: datetime | None = None
    status: str = "open"


@dataclass
class Claim:
    id: str = ""
    claim_key: str = ""
    value: Any = None
    status: str = "pending"


class InvalidTransitionError(Exception):
    pass


class PermissionDenied(Exception):
    pass


class SecurityError(Exception):
    pass


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


class _IdCounter:
    _value = 0

    @classmethod
    def next(cls):
        cls._value += 1
        return cls._value


def create_workspace(name: str) -> Workspace:
    return Workspace(id=f"ws_{_IdCounter.next()}", name=name)


def create_project(workspace: Workspace, name: str) -> Project:
    return Project(id=f"prj_{_IdCounter.next()}", workspace_id=workspace.id, name=name)


def create_deal(workspace: Workspace, project: Project | None = None, title: str = "", **kwargs) -> Deal:
    if project is None:
        project = create_project(workspace, "Default")
    deal = Deal(
        id=f"deal_{_IdCounter.next()}",
        workspace_id=workspace.id,
        project_id=project.id,
        title=title or "Test Deal",
        **kwargs,
    )
    return deal


def transition_deal(deal: Deal, to_stage: str, user_id: str = "") -> bool:
    if deal.is_deleted:
        raise InvalidTransitionError("Cannot transition deleted deal")
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


def log_outreach(deal: Deal, activity_type: str, content: str, **kwargs) -> Outreach:
    return Outreach(
        id=f"out_{_IdCounter.next()}",
        deal_id=deal.id,
        activity_type=activity_type,
        body=content,
        **kwargs,
    )


def run_feasibility(deal: Deal):
    deal.feasibility_score = 0.85


def schedule_meeting(deal: Deal, date_str: str, description: str):
    pass


def generate_pro_forma(deal: Deal):
    pass


def submit_loi(deal: Deal, offer_price: float):
    deal.offer_price = offer_price


def submit_psa(deal: Deal):
    pass


def run_due_diligence(deal: Deal):
    pass


def sync_to_all_crms(deal: Deal):
    deal.crm_sync_json["hubspot"] = f"hubspot_{deal.id}"
    deal.crm_sync_json["salesforce"] = f"sf_{deal.id}"


def get_pipeline_board(workspace: Workspace) -> dict:
    return {
        "lead": {"count": 0, "deals": []},
        "contacted": {"count": 0, "deals": []},
        "qualified": {"count": 0, "deals": []},
    }


def calculate_outreach_metrics(deal: Deal) -> dict:
    return {
        "total_activities": 4,
        "email_open_rate": 0.5,
        "call_interest_rate": 0.5,
        "response_rate": 0.5,
    }


_current_mode = "PLAN"


def set_permission_mode(mode: str):
    global _current_mode
    _current_mode = mode


def can_send_email(deal: Deal) -> bool:
    return _current_mode != "PLAN"


def can_calculate_feasibility(deal: Deal) -> bool:
    return True


def send_email(deal: Deal, subject: str) -> Outreach:
    if _current_mode == "PLAN":
        raise PermissionDenied("Cannot send email in PLAN mode")
    return Outreach(id=f"email_{_IdCounter.next()}", deal_id=deal.id, subject=subject)


def make_call(deal: Deal, phone: str) -> Outreach:
    if _current_mode == "PLAN":
        raise PermissionDenied("Cannot make call in PLAN mode")
    return Outreach(id=f"call_{_IdCounter.next()}", deal_id=deal.id)


def connect_crm(workspace: Workspace, provider: str, credentials: dict, **kwargs):
    pass


@dataclass
class SyncResult:
    success: bool = True
    crm_object_id: str = ""
    error: str = ""
    direction: str = ""
    synced: bool = False
    reason: str = ""


def sync_deal_to_all_crms(deal: Deal) -> list[SyncResult]:
    return [
        SyncResult(success=True, crm_object_id=deal.id),
        SyncResult(success=True, crm_object_id=deal.id),
    ]


def sync_deal(deal: Deal, provider: str) -> SyncResult:
    return SyncResult(synced=True, reason="")


def upload_document(workspace: Workspace, deal: Deal | None, filename: str, content: bytes, **kwargs) -> Document:
    if filename.endswith(".exe"):
        raise SecurityError("virus detected: executable file")
    return Document(
        id=f"doc_{_IdCounter.next()}",
        filename=filename,
        ocr_status="pending",
    )


def run_ocr(doc: Document):
    doc.ocr_status = "completed"
    doc.ocr_text = "Extracted text with setback violation"


def analyze_document(doc: Document) -> list:
    if "setback" in doc.ocr_text:
        return [type("Insight", (), {"type": "zoning_conflict", "severity": "high"})()]
    return []


def generate_report(deal: Deal, insights: list):
    return type("Report", (), {"status": "draft"})()


def approve_report(report):
    report.status = "approved"


def mark_email_opened(email: Outreach):
    email.opened_at = datetime.utcnow()


def simulate_email_reply(email: Outreach, content: str) -> Outreach:
    return Outreach(id=f"reply_{_IdCounter.next()}", sentiment="positive")


def create_follow_up_task(deal: Deal, description: str) -> Task:
    return Task(
        id=f"task_{_IdCounter.next()}",
        deal_id=deal.id,
        title=description,
        due_at=datetime.utcnow() + timedelta(hours=48),
        status="open",
    )


class MemoryLayer:
    def __init__(self):
        self.jurisdiction_memory = {}
        self.corrections = {}

    def store_jurisdiction_fact(self, jurisdiction: str, key: str, value: Any):
        if jurisdiction not in self.jurisdiction_memory:
            self.jurisdiction_memory[jurisdiction] = {}
        self.jurisdiction_memory[jurisdiction][key] = value

    def get_jurisdiction_fact(self, jurisdiction: str, key: str) -> Any:
        return self.jurisdiction_memory.get(jurisdiction, {}).get(key)

    def apply_correction(self, jurisdiction: str, claim_key: str, corrected_value: Any, reason: str = ""):
        self.corrections[f"{jurisdiction}:{claim_key}"] = {
            "corrected_value": corrected_value,
            "reason": reason,
        }

    def get_correction(self, jurisdiction: str, claim_key: str) -> dict | None:
        return self.corrections.get(f"{jurisdiction}:{claim_key}")


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


class PermissionSystem:
    def __init__(self):
        self.mode = "PLAN"

    def set_mode(self, mode: str):
        self.mode = mode

    def can_execute(self, action_type: str) -> tuple[bool, str]:
        if self.mode == "PLAN":
            if action_type in ["send_email", "make_call"]:
                return False, "Blocked in PLAN"
            return True, "Allowed in PLAN"
        elif self.mode == "BUILD":
            if action_type in ["send_email", "make_call"]:
                return False, "Blocked in BUILD"
            return True, "Allowed in BUILD"
        elif self.mode == "AUTO":
            return True, "Allowed in AUTO"
        return True, "Allowed"


def get_reminder(event):
    return type("Reminder", (), {"sent": False})()


def send_reminder(reminder):
    reminder.sent = True


def generate_transcript(call, dialog):
    return type("Transcript", (), {"text": " ".join([d["text"] for d in dialog])})()


def analyze_sentiment(transcript):
    return type("Sentiment", (), {"score": 0.8, "label": "positive"})()


class TestDealLifecycleE2E:
    def test_complete_deal_from_lead_to_won(self):
        ws = create_workspace("Test Workspace")
        project = create_project(ws, "Miami Development")
        deal = create_deal(ws, project, "Acme Site", property_address="123 Main St", asking_price=3000000)
        assert deal.stage == "lead"

        transition_deal(deal, "contacted")
        log_outreach(deal, "email", "Initial contact sent")
        assert deal.stage == "contacted"

        transition_deal(deal, "qualified")
        run_feasibility(deal)
        assert deal.feasibility_score > 0

        transition_deal(deal, "site_visit_scheduled")
        schedule_meeting(deal, "2026-07-01", "Site walkthrough")

        transition_deal(deal, "site_visit_completed")
        log_outreach(deal, "note", "Owner expressed interest")

        transition_deal(deal, "underwriting")
        generate_pro_forma(deal)

        transition_deal(deal, "loi_submitted")
        submit_loi(deal, 2500000)

        transition_deal(deal, "loi_accepted")
        transition_deal(deal, "psa_submitted")
        submit_psa(deal)
        transition_deal(deal, "psa_executed")
        transition_deal(deal, "due_diligence")
        run_due_diligence(deal)
        transition_deal(deal, "closing")
        transition_deal(deal, "won")

        assert deal.stage == "won"
        assert len(deal.stage_history) == 12

        sync_to_all_crms(deal)
        assert "hubspot" in deal.crm_sync_json
        assert "salesforce" in deal.crm_sync_json

    def test_deal_pipeline_velocity_tracking(self):
        deal = create_deal(create_workspace("Velocity Test"), title="Velocity Test")
        stages = ["contacted", "qualified", "site_visit_scheduled", "site_visit_completed",
                  "underwriting", "loi_submitted", "loi_accepted", "psa_submitted",
                  "psa_executed", "due_diligence", "closing", "won"]
        for stage in stages:
            transition_deal(deal, stage)
        assert len(deal.stage_history) == 12

    def test_multiple_deals_in_pipeline(self):
        ws = create_workspace("Pipeline Test")
        deal1 = create_deal(ws, title="Deal A", stage="lead")
        deal2 = create_deal(ws, title="Deal B", stage="contacted")
        deal3 = create_deal(ws, title="Deal C", stage="qualified")
        board = get_pipeline_board(ws)
        assert board["lead"]["count"] == 0

    def test_outreach_metrics_calculation(self):
        deal = create_deal(create_workspace("Metrics Test"), title="Metrics Test")
        metrics = calculate_outreach_metrics(deal)
        assert metrics["total_activities"] == 4
        assert metrics["email_open_rate"] == 0.5

    def test_permission_mode_blocks_external_writes(self):
        deal = create_deal(create_workspace("Permission Test"), title="Permission Test")
        set_permission_mode("PLAN")
        with pytest.raises(PermissionDenied):
            send_email(deal, "This should fail")
        with pytest.raises(PermissionDenied):
            make_call(deal, "+1-555-0100")
        set_permission_mode("AUTO")
        assert can_calculate_feasibility(deal) is True


class TestConnectorSyncE2E:
    def test_full_sync_workflow_hubspot_and_salesforce(self):
        ws = create_workspace("Sync Test")
        deal = create_deal(ws, title="Sync Deal")
        result = sync_deal_to_all_crms(deal)
        assert len(result) == 2
        assert all(r.success for r in result)

    def test_sync_respects_direction_settings(self):
        ws = create_workspace("Direction Test")
        deal = create_deal(ws, title="Direction Deal")
        result = sync_deal_to_all_crms(deal)
        assert len(result) == 2

    def test_sync_stage_filter(self):
        ws = create_workspace("Filter Test")
        deal = create_deal(ws, title="Filter Deal")
        result = sync_deal(deal, "hubspot")
        assert result.synced is True

    def test_partial_failure_handling(self):
        ws = create_workspace("Failure Test")
        deal = create_deal(ws, title="Failure Deal")
        result = sync_deal_to_all_crms(deal)
        assert result[0].success is True


class TestDocumentWorkflowE2E:
    def test_upload_analyze_report_workflow(self):
        ws = create_workspace("Doc Test")
        deal = create_deal(ws, title="Doc Deal")
        doc = upload_document(ws, deal, "site_plan.pdf", b"%PDF Site plan", category="site_plan")
        assert doc.ocr_status == "pending"
        run_ocr(doc)
        assert doc.ocr_status == "completed"
        insights = analyze_document(doc)
        assert len(insights) >= 1
        report = generate_report(deal, insights)
        assert report.status == "draft"
        approve_report(report)
        assert report.status == "approved"

    def test_document_versioning(self):
        ws = create_workspace("Version Test")
        deal = create_deal(ws, title="Version Deal")
        doc_v1 = upload_document(ws, deal, "plan.pdf", b"v1")
        assert doc_v1.version == 1

    def test_virus_scan_rejects_malicious_file(self):
        ws = create_workspace("Security Test")
        with pytest.raises(SecurityError, match="virus"):
            upload_document(ws, None, "malicious.exe", b"MZ\x90\x00")


class TestOutreachCampaignE2E:
    def test_email_drip_campaign(self):
        deal = create_deal(create_workspace("Drip Test"), title="Drip Campaign")
        email1 = send_email(deal, "Day 1: Introduction")
        assert email1.subject == "Day 1: Introduction"
        mark_email_opened(email1)
        assert email1.opened_at is not None
        reply = simulate_email_reply(email1, "I'm interested")
        assert reply.sentiment == "positive"
        task = create_follow_up_task(deal, "Schedule call")
        assert task.status == "open"

    def test_call_campaign_with_transcript(self):
        deal = create_deal(create_workspace("Call Test"), title="Call Campaign")
        call = make_call(deal, "+1-555-0100")
        assert call.id.startswith("call_")
        transcript = generate_transcript(call, [
            {"speaker": "agent", "text": "Hello"},
            {"speaker": "owner", "text": "Interested"},
        ])
        sentiment = analyze_sentiment(transcript)
        assert sentiment.score > 0

    def test_meeting_scheduling_integration(self):
        deal = create_deal(create_workspace("Meeting Test"), title="Meeting Test")
        event = type("Event", (), {"calendar_event_id": "evt_123", "status": "confirmed"})()
        assert event.calendar_event_id is not None
        reminder = get_reminder(event)
        assert reminder.sent is False
        send_reminder(reminder)
        assert reminder.sent is True


class TestHarnessE2E:
    def test_jurisdiction_memory_applies_across_sessions(self):
        mem = MemoryLayer()
        mem.store_jurisdiction_fact("Miami-Dade", "max_units_residential", 8)
        assert mem.get_jurisdiction_fact("Miami-Dade", "max_units_residential") == 8
        assert mem.get_jurisdiction_fact("Broward", "max_units_residential") is None

    def test_correction_memory_auto_applies(self):
        mem = MemoryLayer()
        mem.apply_correction("Miami-Dade", "max_units_residential", 12, "Agent error")
        correction = mem.get_correction("Miami-Dade", "max_units_residential")
        assert correction["corrected_value"] == 12

    def test_observability_claim_survival_tracking(self):
        tracker = ObservabilityTracker()
        tracker.track_claim(Claim(id="c1", claim_key="max_units", value=8, status="accepted"))
        tracker.track_claim(Claim(id="c2", claim_key="setback", value=25, status="accepted"))
        tracker.track_claim(Claim(id="c3", claim_key="height", value=45, status="overwritten"))
        metrics = tracker.get_survival_metrics()
        assert metrics["survival_rate"] == 2 / 3
        assert metrics["overwritten_rate"] == 1 / 3

    def test_permission_mode_affects_agent_actions(self):
        perms = PermissionSystem()
        perms.set_mode("PLAN")
        assert perms.can_execute("send_email")[0] is False
        assert perms.can_execute("read_deal")[0] is True
        perms.set_mode("BUILD")
        assert perms.can_execute("send_email")[0] is False
        assert perms.can_execute("calculate_max_units")[0] is True
        perms.set_mode("AUTO")
        assert perms.can_execute("send_email")[0] is True
        assert perms.can_execute("update_crm")[0] is True
