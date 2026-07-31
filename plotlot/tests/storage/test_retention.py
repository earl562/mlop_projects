from __future__ import annotations

from datetime import UTC, datetime, timedelta

from plotlot.storage.lifecycle import LifecycleRecord, RetentionDecision, decide_retention


NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_expired_record_is_deleted_for_owning_tenant() -> None:
    record = LifecycleRecord(
        tenant_id="tenant-a",
        object_key="raw/a",
        retain_until=NOW - timedelta(seconds=1),
        legal_hold=False,
        deletion_requested_at=NOW,
    )

    assert decide_retention("tenant-a", record, NOW) is RetentionDecision.DELETE


def test_legal_hold_prevents_deletion_after_retention_clock_advance() -> None:
    record = LifecycleRecord(
        tenant_id="tenant-a",
        object_key="raw/a",
        retain_until=NOW - timedelta(days=30),
        legal_hold=True,
        deletion_requested_at=NOW - timedelta(days=1),
    )

    assert decide_retention("tenant-a", record, NOW) is RetentionDecision.HOLD


def test_other_tenant_cannot_delete_record() -> None:
    record = LifecycleRecord(
        tenant_id="tenant-a",
        object_key="raw/a",
        retain_until=NOW - timedelta(days=30),
        legal_hold=False,
        deletion_requested_at=NOW,
    )

    assert decide_retention("tenant-b", record, NOW) is RetentionDecision.DENY
