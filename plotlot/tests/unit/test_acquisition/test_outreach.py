"""Tests for Outreach Activity Logging (AC-1.5)."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class FakeOutreach:
    id: str = ""
    deal_id: str = ""
    activity_type: str = ""
    direction: str = "outbound"
    subject: str = ""
    body: str = ""
    status: str = "draft"
    sentiment: str = ""
    call_outcome: str = ""
    created_at: str = ""


@dataclass
class FakeFollowUpTask:
    id: str = ""
    deal_id: str = ""
    title: str = ""
    due_at: str = ""
    status: str = "open"


class OutreachLogger:
    def __init__(self):
        self.activities = []
        self.tasks = []

    def log_email(self, deal_id: str, subject: str, body: str) -> FakeOutreach:
        activity = FakeOutreach(
            id=f"act_{len(self.activities)}",
            deal_id=deal_id,
            activity_type="email",
            subject=subject,
            body=body,
            status="sent",
            created_at=datetime.utcnow().isoformat(),
        )
        self.activities.append(activity)
        return activity

    def log_call(self, deal_id: str, outcome: str, sentiment: str = "") -> FakeOutreach:
        activity = FakeOutreach(
            id=f"act_{len(self.activities)}",
            deal_id=deal_id,
            activity_type="call",
            call_outcome=outcome,
            sentiment=sentiment,
            status="completed",
            created_at=datetime.utcnow().isoformat(),
        )
        self.activities.append(activity)
        if outcome == "interested":
            task = FakeFollowUpTask(
                id=f"task_{len(self.tasks)}",
                deal_id=deal_id,
                title="Follow up with interested owner",
                due_at=(datetime.utcnow() + timedelta(hours=48)).isoformat(),
            )
            self.tasks.append(task)
        return activity

    def get_deal_activities(self, deal_id: str) -> list[FakeOutreach]:
        return [a for a in self.activities if a.deal_id == deal_id]


class TestOutreachLogging:
    def test_email_creates_outreach_record(self):
        logger = OutreachLogger()
        activity = logger.log_email("deal_001", "Property Interest", "Hello,")
        assert activity.deal_id == "deal_001"
        assert activity.activity_type == "email"
        assert activity.status == "sent"

    def test_call_logged_with_outcome(self):
        logger = OutreachLogger()
        activity = logger.log_call("deal_001", "interested", "positive")
        assert activity.activity_type == "call"
        assert activity.call_outcome == "interested"
        assert activity.sentiment == "positive"

    def test_interested_call_creates_follow_up_task(self):
        logger = OutreachLogger()
        logger.log_call("deal_001", "interested")
        assert len(logger.tasks) == 1
        assert logger.tasks[0].deal_id == "deal_001"
        assert logger.tasks[0].status == "open"

    def test_not_interested_call_no_task(self):
        logger = OutreachLogger()
        logger.log_call("deal_001", "not_interested")
        assert len(logger.tasks) == 0

    def test_get_deal_activities_filters_correctly(self):
        logger = OutreachLogger()
        logger.log_email("deal_001", "A", "Body")
        logger.log_email("deal_002", "B", "Body")
        logger.log_call("deal_001", "interested")
        activities = logger.get_deal_activities("deal_001")
        assert len(activities) == 2
        assert all(a.deal_id == "deal_001" for a in activities)
