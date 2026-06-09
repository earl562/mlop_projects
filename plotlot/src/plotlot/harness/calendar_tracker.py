"""Calendar + permit workflow tracking.

Calendar: follow-up reminders, contract deadlines, closing dates.
Permit workflow: application status, agency contacts, expiration tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class CalendarEvent:
    event_id: str
    lead_id: str
    event_type: str  # follow_up, contract_deadline, closing, permit_expiry, inspection
    title: str
    due_date: str
    completed: bool = False
    notes: str = ""


@dataclass  
class PermitApplication:
    permit_id: str
    lead_id: str
    permit_type: str
    agency: str
    status: str = "not_started"  # not_started, submitted, under_review, approved, denied, expired
    submitted_date: str = ""
    estimated_weeks: int = 0
    fee_amount: float = 0.0
    notes: str = ""


class CalendarTracker:
    """Track all deadlines across the acquisition pipeline."""

    def __init__(self):
        self._events: dict[str, CalendarEvent] = {}

    def schedule_follow_up(self, lead_id: str, days: int = 7) -> CalendarEvent:
        due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()[:10]
        eid = f"fu-{lead_id}-{due}"
        event = CalendarEvent(event_id=eid, lead_id=lead_id, event_type="follow_up", title=f"Follow up with lead {lead_id}", due_date=due)
        self._events[eid] = event
        return event

    def schedule_contract_deadline(self, lead_id: str, days: int = 60) -> CalendarEvent:
        due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()[:10]
        eid = f"contract-{lead_id}"
        event = CalendarEvent(event_id=eid, lead_id=lead_id, event_type="contract_deadline", title=f"Contract deadline for {lead_id}", due_date=due)
        self._events[eid] = event
        return event

    def due_today(self) -> list[CalendarEvent]:
        today = datetime.now(timezone.utc).isoformat()[:10]
        return [e for e in self._events.values() if e.due_date <= today and not e.completed]

    def due_this_week(self) -> list[CalendarEvent]:
        today = datetime.now(timezone.utc)
        week_end = today + timedelta(days=7)
        return [e for e in self._events.values() if today.isoformat()[:10] <= e.due_date <= week_end.isoformat()[:10] and not e.completed]

    def complete(self, event_id: str) -> None:
        if event_id in self._events:
            self._events[event_id].completed = True


class PermitTracker:
    """Track permit applications through the approval process."""

    def __init__(self):
        self._permits: dict[str, PermitApplication] = {}

    def add_permit(self, lead_id: str, permit_type: str, agency: str, estimated_weeks: int, fee: float = 0) -> PermitApplication:
        pid = f"permit-{lead_id}-{permit_type.replace(' ','_')}"
        permit = PermitApplication(permit_id=pid, lead_id=lead_id, permit_type=permit_type, agency=agency, estimated_weeks=estimated_weeks, fee_amount=fee)
        self._permits[pid] = permit
        return permit

    def add_from_requirements(self, lead_id: str, requirements: list[dict[str, Any]]) -> list[PermitApplication]:
        """Add all permits from identify_permits() output."""
        added = []
        for req in requirements:
            if req.get("required"):
                permit = self.add_permit(lead_id, req["permit"], req["agency"], req.get("timeline_weeks", 4))
                added.append(permit)
        return added

    def by_status(self, status: str) -> list[PermitApplication]:
        return [p for p in self._permits.values() if p.status == status]

    def for_lead(self, lead_id: str) -> list[PermitApplication]:
        return [p for p in self._permits.values() if p.lead_id == lead_id]

    def update_status(self, permit_id: str, status: str) -> None:
        if permit_id in self._permits:
            self._permits[permit_id].status = status
            if status == "submitted":
                self._permits[permit_id].submitted_date = datetime.now(timezone.utc).isoformat()[:10]

    def stats(self) -> dict[str, Any]:
        statuses = {}
        for p in self._permits.values():
            statuses[p.status] = statuses.get(p.status, 0) + 1
        return {"total": len(self._permits), "by_status": statuses, "pending": len(self.by_status("submitted")) + len(self.by_status("under_review"))}
