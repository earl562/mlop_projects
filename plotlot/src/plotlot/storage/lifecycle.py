from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RetentionDecision(StrEnum):
    KEEP = "keep"
    DELETE = "delete"
    HOLD = "hold"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    tenant_id: str
    object_key: str
    retain_until: datetime
    legal_hold: bool
    deletion_requested_at: datetime | None


def decide_retention(
    requesting_tenant_id: str,
    record: LifecycleRecord,
    now: datetime,
) -> RetentionDecision:
    if requesting_tenant_id != record.tenant_id:
        return RetentionDecision.DENY
    if record.legal_hold:
        return RetentionDecision.HOLD
    if record.deletion_requested_at is None or now < record.retain_until:
        return RetentionDecision.KEEP
    return RetentionDecision.DELETE
