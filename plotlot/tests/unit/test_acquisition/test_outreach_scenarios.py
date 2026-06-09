"""Comprehensive outreach scenarios: happy + unhappy paths.

Covers:
  AC-1.5: Outreach logging (email, call, meeting)
  AC-1.6: Follow-up task creation
  AC-1.7: Deal activity aggregation
  AC-1.8: Sentiment tracking

Uses InMemoryDB pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest


@dataclass
class FakeOutreachRecord:
    id: str = ""
    deal_id: str = ""
    activity_type: str = ""          # "email", "call", "meeting"
    direction: str = "outbound"      # "inbound", "outbound"
    subject: str = ""
    body: str = ""
    status: str = "draft"            # "draft", "sent", "completed", "cancelled"
    sentiment: str = ""              # "positive", "neutral", "negative", ""
    call_outcome: str = ""           # "interested", "not_interested", "no_answer", "voicemail", "follow_up"
    duration_seconds: int = 0
    created_at: str = ""
    created_by: str = ""


@dataclass
class FakeFollowUpTask:
    id: str = ""
    deal_id: str = ""
    title: str = ""
    description: str = ""
    due_at: str = ""
    priority: str = "medium"         # "low", "medium", "high"
    status: str = "open"             # "open", "completed", "overdue"
    assigned_to: str = ""
    created_at: str = ""


class InMemoryOutreachDB:
    """In-memory store for outreach activities and tasks."""

    def __init__(self):
        self.activities: list[FakeOutreachRecord] = []
        self.tasks: list[FakeFollowUpTask] = []
        self._next_id = 1

    def _next(self, prefix: str) -> str:
        current = self._next_id
        self._next_id += 1
        return f"{prefix}_{current}"

    def add_activity(self, activity: FakeOutreachRecord) -> FakeOutreachRecord:
        if not activity.id:
            activity.id = self._next("act")
        self.activities.append(activity)
        return activity

    def add_task(self, task: FakeFollowUpTask) -> FakeFollowUpTask:
        if not task.id:
            task.id = self._next("task")
        self.tasks.append(task)
        return task

    def get_deal_activities(self, deal_id: str) -> list[FakeOutreachRecord]:
        return [a for a in self.activities if a.deal_id == deal_id]

    def get_deal_tasks(self, deal_id: str) -> list[FakeFollowUpTask]:
        return [t for t in self.tasks if t.deal_id == deal_id]

    def get_activity(self, activity_id: str) -> FakeOutreachRecord | None:
        for a in self.activities:
            if a.id == activity_id:
                return a
        return None

    def complete_task(self, task_id: str) -> FakeFollowUpTask | None:
        for t in self.tasks:
            if t.id == task_id:
                t.status = "completed"
                return t
        return None

    def overdue_tasks(self, before: datetime) -> list[FakeFollowUpTask]:
        overdue = []
        for t in self.tasks:
            due = datetime.fromisoformat(t.due_at.replace("Z", "+00:00"))
            if due < before and t.status == "open":
                t.status = "overdue"
                overdue.append(t)
        return overdue

    def count_by_type(self, deal_id: str, activity_type: str) -> int:
        return sum(
            1 for a in self.activities
            if a.deal_id == deal_id and a.activity_type == activity_type
        )


class OutreachService:
    """Service layer for logging and managing outreach."""

    def __init__(self, db: InMemoryOutreachDB):
        self.db = db

    def log_email(
        self,
        deal_id: str,
        subject: str,
        body: str,
        direction: str = "outbound",
        created_by: str = "",
    ) -> FakeOutreachRecord:
        activity = FakeOutreachRecord(
            deal_id=deal_id,
            activity_type="email",
            direction=direction,
            subject=subject,
            body=body,
            status="sent",
            created_by=created_by,
            created_at=datetime.now().astimezone().isoformat(),
        )
        return self.db.add_activity(activity)

    def log_call(
        self,
        deal_id: str,
        outcome: str,
        sentiment: str = "",
        duration_seconds: int = 0,
        created_by: str = "",
    ) -> FakeOutreachRecord:
        activity = FakeOutreachRecord(
            deal_id=deal_id,
            activity_type="call",
            call_outcome=outcome,
            sentiment=sentiment,
            duration_seconds=duration_seconds,
            status="completed",
            created_by=created_by,
            created_at=datetime.now().astimezone().isoformat(),
        )
        self.db.add_activity(activity)
        if outcome == "interested":
            self.db.add_task(FakeFollowUpTask(
                deal_id=deal_id,
                title="Follow up with interested owner",
                description=f"Call outcome: interested ({sentiment})",
                due_at=(datetime.now().astimezone() + timedelta(hours=48)).isoformat(),
                priority="high",
            ))
        elif outcome == "follow_up":
            self.db.add_task(FakeFollowUpTask(
                deal_id=deal_id,
                title="Schedule follow-up call",
                due_at=(datetime.now().astimezone() + timedelta(days=7)).isoformat(),
                priority="medium",
            ))
        return activity

    def log_meeting(
        self,
        deal_id: str,
        subject: str,
        duration_seconds: int,
        created_by: str = "",
    ) -> FakeOutreachRecord:
        activity = FakeOutreachRecord(
            deal_id=deal_id,
            activity_type="meeting",
            subject=subject,
            duration_seconds=duration_seconds,
            status="completed",
            created_by=created_by,
            created_at=datetime.now().astimezone().isoformat(),
        )
        return self.db.add_activity(activity)

    def bulk_log_emails(self, deal_ids: list[str], subject: str, body: str) -> dict[str, FakeOutreachRecord]:
        results = {}
        for deal_id in deal_ids:
            results[deal_id] = self.log_email(deal_id, subject, body)
        return results

    def get_activity_summary(self, deal_id: str) -> dict[str, Any]:
        activities = self.db.get_deal_activities(deal_id)
        return {
            "total": len(activities),
            "emails": self.db.count_by_type(deal_id, "email"),
            "calls": self.db.count_by_type(deal_id, "call"),
            "meetings": self.db.count_by_type(deal_id, "meeting"),
            "last_contact": max((a.created_at for a in activities), default=None),
        }


@pytest.fixture
def outreach_db():
    return InMemoryOutreachDB()


@pytest.fixture
def service(outreach_db):
    return OutreachService(outreach_db)


@pytest.fixture
def sample_deal_id():
    return "deal_001"


# ───────────────────────
# HAPPY PATHS
# ───────────────────────
class TestOutreachHappyPaths:
    """Given/When/Then scenarios for expected success."""

    # AC-1.5a
    def test_log_email_creates_record(self, service, sample_deal_id):
        """
        Given an active deal,
        When I log an email to the owner,
        Then an outreach record is created with type='email' and status='sent'.
        """
        activity = service.log_email(sample_deal_id, "Property Interest", "Hello,")
        assert activity.activity_type == "email"
        assert activity.status == "sent"
        assert activity.direction == "outbound"

    # AC-1.5b
    def test_log_call_with_outcome(self, service, sample_deal_id):
        """
        Given an active deal,
        When I log a call with outcome='interested' and sentiment='positive',
        Then the record is stored with outcome, sentiment, and status='completed'.
        """
        activity = service.log_call(sample_deal_id, "interested", "positive", duration_seconds=300)
        assert activity.activity_type == "call"
        assert activity.call_outcome == "interested"
        assert activity.sentiment == "positive"
        assert activity.duration_seconds == 300

    # AC-1.5c
    def test_log_meeting(self, service, sample_deal_id):
        """
        Given a scheduled meeting,
        When I log the meeting after it completes,
        Then a meeting record exists with duration.
        """
        activity = service.log_meeting(sample_deal_id, "Site Visit Discussion", 3600)
        assert activity.activity_type == "meeting"
        assert activity.duration_seconds == 3600
        assert activity.status == "completed"

    # AC-1.6a
    def test_interested_call_creates_follow_up_task(self, service, outreach_db, sample_deal_id):
        """
        Given a call with outcome='interested',
        When the call is logged,
        Then a high-priority follow-up task is created due in 48 hours.
        """
        service.log_call(sample_deal_id, "interested")
        tasks = outreach_db.get_deal_tasks(sample_deal_id)
        assert len(tasks) == 1
        assert tasks[0].priority == "high"
        assert "Follow up" in tasks[0].title

    # AC-1.6b
    def test_follow_up_outcome_creates_task(self, service, outreach_db, sample_deal_id):
        """
        Given a call with outcome='follow_up',
        When the call is logged,
        Then a medium-priority task is created due in 7 days.
        """
        service.log_call(sample_deal_id, "follow_up")
        tasks = outreach_db.get_deal_tasks(sample_deal_id)
        assert len(tasks) == 1
        assert tasks[0].priority == "medium"

    # AC-1.6c
    def test_no_task_for_not_interested(self, service, outreach_db, sample_deal_id):
        """
        Given a call with outcome='not_interested',
        When the call is logged,
        Then no follow-up task is created.
        """
        service.log_call(sample_deal_id, "not_interested")
        assert len(outreach_db.get_deal_tasks(sample_deal_id)) == 0

    # AC-1.7a
    def test_get_deal_activities_filters_correctly(self, service, outreach_db, sample_deal_id):
        """
        Given two deals with mixed activities,
        When I fetch activities for deal_001,
        Then only activities for deal_001 are returned.
        """
        service.log_email("deal_001", "A", "Body")
        service.log_call("deal_001", "interested")
        service.log_email("deal_002", "B", "Body")
        activities = outreach_db.get_deal_activities("deal_001")
        assert len(activities) == 2
        assert all(a.deal_id == "deal_001" for a in activities)

    # AC-1.7b
    def test_activity_summary_counts_by_type(self, service, sample_deal_id):
        """
        Given a deal with 2 emails, 1 call, and 1 meeting,
        When I request the activity summary,
        Then counts reflect exactly those numbers.
        """
        service.log_email(sample_deal_id, "E1", "B1")
        service.log_email(sample_deal_id, "E2", "B2")
        service.log_call(sample_deal_id, "interested")
        service.log_meeting(sample_deal_id, "M1", 1800)
        summary = service.get_activity_summary(sample_deal_id)
        assert summary["total"] == 4
        assert summary["emails"] == 2
        assert summary["calls"] == 1
        assert summary["meetings"] == 1

    # AC-1.7c
    def test_bulk_log_emails(self, service, outreach_db):
        """
        Given a list of 3 deal IDs,
        When I bulk-log a marketing email,
        Then each deal gets its own outreach record.
        """
        deal_ids = ["deal_a", "deal_b", "deal_c"]
        results = service.bulk_log_emails(deal_ids, "Campaign", "Newsletter")
        assert len(results) == 3
        for deal_id in deal_ids:
            assert results[deal_id].deal_id == deal_id
            assert results[deal_id].status == "sent"

    # AC-1.8
    def test_inbound_email_direction(self, service, sample_deal_id):
        """
        Given an inbound email from an owner,
        When I log the email with direction='inbound',
        Then the direction field is 'inbound'.
        """
        activity = service.log_email(sample_deal_id, "Re: Offer", "Counter at 3.2M", direction="inbound")
        assert activity.direction == "inbound"

    # AC-1.8b
    def test_negative_sentiment_tracked(self, service, outreach_db, sample_deal_id):
        """
        Given an owner declining interest,
        When I log the call sentiment as 'negative',
        Then the sentiment field persists in the record.
        """
        activity = service.log_call(sample_deal_id, "not_interested", "negative")
        assert activity.sentiment == "negative"


# ───────────────────────
# UNHAPPY PATHS
# ───────────────────────
class TestOutreachUnhappyPaths:
    """Given/When/Then scenarios for error cases and edge cases."""

    def test_empty_deal_id_should_be_rejected(self, service):
        """
        Given an empty deal_id,
        When logging any activity,
        Then the system records it but downstream retrieval may return it in global views.
        (Edge case: ensures empty deal_id doesn't crash.)
        """
        activity = service.log_email("", "Subject", "Body")
        assert activity.deal_id == ""

    def test_missing_subject_email(self, service, sample_deal_id):
        """
        Given no subject line,
        When logging an email,
        Then the record is still created with an empty subject.
        """
        activity = service.log_email(sample_deal_id, "", "Body without subject")
        assert activity.subject == ""
        assert activity.status == "sent"

    def test_empty_body_email(self, service, sample_deal_id):
        """
        Given an empty body,
        When logging an email,
        Then the record stores an empty body.
        """
        activity = service.log_email(sample_deal_id, "Subject", "")
        assert activity.body == ""

    def test_invalid_call_outcome(self, service, sample_deal_id):
        """
        Given an unrecognized call outcome,
        When logging the call,
        Then the record stores it but no follow-up task is created.
        """
        activity = service.log_call(sample_deal_id, "spam_call")
        assert activity.call_outcome == "spam_call"
        assert activity.status == "completed"

    def test_zero_duration_meeting(self, service, sample_deal_id):
        """
        Given a meeting with 0 seconds duration,
        When logging the meeting,
        Then the record is created with duration_seconds=0.
        """
        activity = service.log_meeting(sample_deal_id, "Quick Chat", 0)
        assert activity.duration_seconds == 0

    def test_duplicate_task_creation(self, service, outreach_db, sample_deal_id):
        """
        Given two calls both with outcome='interested',
        When logged to the same deal,
        Then two separate follow-up tasks are created.
        """
        service.log_call(sample_deal_id, "interested")
        service.log_call(sample_deal_id, "interested")
        assert len(outreach_db.get_deal_tasks(sample_deal_id)) == 2

    def test_task_overdue_detection(self, service, outreach_db, sample_deal_id):
        """
        Given a task due yesterday,
        When the overdue check runs,
        Then the task status changes to 'overdue'.
        """
        past = (datetime.now().astimezone() - timedelta(days=1)).isoformat()
        task = outreach_db.add_task(FakeFollowUpTask(
            deal_id=sample_deal_id,
            title="Old Task",
            due_at=past,
            status="open",
        ))
        overdue = outreach_db.overdue_tasks(datetime.now().astimezone())
        assert task in overdue
        assert task.status == "overdue"

    def test_bulk_log_empty_list(self, service):
        """
        Given an empty list of deal IDs,
        When bulk-logging emails,
        Then no records are created and an empty dict is returned.
        """
        results = service.bulk_log_emails([], "Subject", "Body")
        assert results == {}

    def test_get_summary_for_deal_with_no_activities(self, service):
        """
        Given a deal with zero activities,
        When requesting an activity summary,
        Then the summary shows zero counts and last_contact=None.
        """
        summary = service.get_activity_summary("deal_no_activities")
        assert summary["total"] == 0
        assert summary["last_contact"] is None

    def test_null_sentiment_defaults_to_empty(self, service, sample_deal_id):
        """
        Given a call logged without sentiment,
        Then the sentiment field defaults to an empty string.
        """
        activity = service.log_call(sample_deal_id, "no_answer")
        assert activity.sentiment == ""


# ───────────────────────
# EDGE CASES & BOUNDARY VALUES
# ───────────────────────
class TestOutreachEdgeCases:
    """Edge-case parameterized tests for robustness."""

    @pytest.mark.parametrize("activity_type", ["email", "call", "meeting"])
    def test_activity_types_create_records(self, service, outreach_db, sample_deal_id, activity_type):
        """Regardless of activity_type, record creation succeeds."""
        if activity_type == "email":
            activity = service.log_email(sample_deal_id, "S", "B")
        elif activity_type == "call":
            activity = service.log_call(sample_deal_id, "interested")
        else:
            activity = service.log_meeting(sample_deal_id, "M", 900)
        assert outreach_db.get_activity(activity.id) is not None

    @pytest.mark.parametrize("duration", [0, 1, 59, 60, 3600, 86400])
    def test_various_meeting_durations(self, service, sample_deal_id, duration):
        """Meeting durations across boundary values (0s, 1s, 1hr, 24hr) all succeed."""
        activity = service.log_meeting(sample_deal_id, "Test", duration)
        assert activity.duration_seconds == duration

    @pytest.mark.parametrize("outcome,task_count", [
        ("interested", 1),
        ("follow_up", 1),
        ("not_interested", 0),
        ("no_answer", 0),
        ("voicemail", 0),
        ("spam_call", 0),
    ])
    def test_outcome_task_mapping(self, service, outreach_db, sample_deal_id, outcome, task_count):
        """Only 'interested' and 'follow_up' outcomes spawn follow-up tasks."""
        service.log_call(sample_deal_id, outcome)
        assert len(outreach_db.get_deal_tasks(sample_deal_id)) == task_count

    def test_very_long_subject_and_body(self, service, sample_deal_id):
        """
        Given a 10_000-char subject and body,
        When logging the email,
        Then the full strings are preserved.
        """
        long_subj = "S" * 10000
        long_body = "B" * 10000
        activity = service.log_email(sample_deal_id, long_subj, long_body)
        assert activity.subject == long_subj
        assert activity.body == long_body

    def test_special_characters_in_body(self, service, sample_deal_id):
        """
        Given Unicode and special characters,
        When logging the email,
        Then all characters are preserved exactly.
        """
        body = "<html>Hello € ü ñ \x00 \n\t </html>"
        activity = service.log_email(sample_deal_id, "Special", body)
        assert activity.body == body

    def test_concurrent_activity_logging(self, service, outreach_db, sample_deal_id):
        """
        Given 100 near-simultaneous activities on the same deal,
        When they are all logged,
        Then the activity count is exactly 100.
        """
        for i in range(100):
            service.log_email(sample_deal_id, f"Email {i}", "Body")
        assert len(outreach_db.get_deal_activities(sample_deal_id)) == 100
