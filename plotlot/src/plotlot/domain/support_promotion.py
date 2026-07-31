from __future__ import annotations

from datetime import datetime

from plotlot.domain.issued_support_registry import (
    VerifiedIssuedSupportRegistry,
    is_verified_issued_support_registry,
    verify_issued_support_receipt,
)
from plotlot.domain.support_ledger import (
    County,
    SupportLedgerEntry,
    SupportPromotionRequest,
)


def apply_support_promotion(
    ledger: tuple[SupportLedgerEntry, ...],
    request: SupportPromotionRequest,
    *,
    receipt_registry: VerifiedIssuedSupportRegistry,
    evaluated_at: datetime,
    enabled_counties: tuple[County, ...] = ("miami-dade",),
) -> tuple[SupportLedgerEntry, ...]:
    coordinates = [
        (entry.county, entry.municipality_lane, entry.workflow, entry.fact_family)
        for entry in ledger
    ]
    if len(set(coordinates)) != len(coordinates):
        raise ValueError("duplicate support coordinate")
    if len(set(request.evidence_receipt_ids)) != len(request.evidence_receipt_ids):
        raise ValueError("duplicate evidence receipt")
    if request.county not in enabled_counties:
        raise ValueError("county is not enabled for support promotion")
    if not is_verified_issued_support_registry(receipt_registry):
        raise ValueError("support registry is unverified")
    failures = {
        verify_issued_support_receipt(
            receipt_registry,
            receipt_id=receipt_id,
            county=request.county,
            municipality_lane=request.municipality_lane,
            workflow=request.workflow,
            fact_family=request.fact_family,
            evaluated_at=evaluated_at,
        )
        for receipt_id in request.evidence_receipt_ids
    }
    if failures != {None}:
        failure = sorted(value for value in failures if value is not None)[0]
        raise ValueError(f"support receipt is {failure}")
    coordinate = (
        request.county,
        request.municipality_lane,
        request.workflow,
        request.fact_family,
    )
    selected = [
        entry
        for entry in ledger
        if (entry.county, entry.municipality_lane, entry.workflow, entry.fact_family) == coordinate
    ]
    if len(selected) != 1:
        raise ValueError("support coordinate is absent or duplicated")
    current = selected[0]
    if current.status == "supported":
        if current.evidence_receipt_ids == request.evidence_receipt_ids:
            return ledger
        raise ValueError("conflicting promotion for supported coordinate")
    return tuple(
        SupportLedgerEntry(
            county=entry.county,
            municipality_lane=entry.municipality_lane,
            workflow=entry.workflow,
            fact_family=entry.fact_family,
            status="supported",
            evidence_receipt_ids=request.evidence_receipt_ids,
        )
        if (entry.county, entry.municipality_lane, entry.workflow, entry.fact_family) == coordinate
        else entry
        for entry in ledger
    )
