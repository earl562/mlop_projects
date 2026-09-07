from __future__ import annotations

from datetime import datetime
from typing import Literal

from plotlot.domain.issued_support_registry import (
    VerifiedIssuedSupportRegistry,
    verify_issued_support_receipt,
)
from plotlot.domain.opportunity_contract_models import (
    OpportunityDecisionInput,
    OpportunityDecisionProjection,
)
from plotlot.domain.support_ledger import WORKFLOW_FACT_FAMILIES


def evaluate_opportunity_decision(
    decision_input: OpportunityDecisionInput,
    *,
    receipt_registry: VerifiedIssuedSupportRegistry,
    evaluated_at: datetime,
) -> OpportunityDecisionProjection:
    statuses = (
        ("property-identity", decision_input.facts.property_identity.status),
        ("local-truth", decision_input.facts.local_truth.status),
        ("constraints-capacity", decision_input.facts.constraints_capacity.status),
        ("market-evidence", decision_input.facts.market_evidence.status),
        ("underwriting", decision_input.facts.underwriting.status),
    )
    blockers = tuple(
        f"{name}-{status}"
        for name, status in statuses
        if status in {"ambiguous", "stale", "conflict"}
    )
    support_failures = tuple(
        verify_issued_support_receipt(
            receipt_registry,
            receipt_id=receipt.evidence_receipt_id,
            county=decision_input.support.county,
            municipality_lane=decision_input.support.municipality_lane,
            workflow=receipt.workflow,
            fact_family=receipt.fact_family,
            evaluated_at=evaluated_at,
        )
        for receipt in decision_input.support.coordinate_receipts
    )
    support_blockers = tuple(
        (
            "support-registry-unverified"
            if failure == "registry-unverified"
            else f"support-receipt-{failure}"
        )
        for failure in dict.fromkeys(support_failures)
        if failure is not None
    )
    support_receipt_count = sum(failure is None for failure in support_failures)
    required_support_count = sum(
        len(definition.fact_families) for definition in WORKFLOW_FACT_FAMILIES
    )
    county_disabled = decision_input.opportunity.county != "miami-dade"
    coverage_blockers = (
        ("county-disabled",)
        if county_disabled
        else (("outside-coverage",) if len(decision_input.support.coordinate_receipts) == 0 else ())
    )
    blocker_codes = blockers + coverage_blockers + support_blockers
    receipts = tuple(
        receipt
        for evidence_receipts in (
            decision_input.facts.property_identity.evidence_receipt_ids,
            decision_input.facts.local_truth.evidence_receipt_ids,
            decision_input.facts.constraints_capacity.evidence_receipt_ids,
            decision_input.facts.market_evidence.evidence_receipt_ids,
            decision_input.facts.underwriting.evidence_receipt_ids,
            tuple(
                receipt.evidence_receipt_id
                for receipt, failure in zip(
                    decision_input.support.coordinate_receipts,
                    support_failures,
                    strict=True,
                )
                if failure is None
            ),
        )
        for receipt in evidence_receipts
    )
    is_thin = decision_input.facts.market_evidence.status == "thin"
    needs_review = decision_input.review.status != "approved"
    support_is_partial = 0 < support_receipt_count < required_support_count
    is_provisional = is_thin or needs_review or support_is_partial
    review: Literal["review-required", "approved"] = (
        "approved" if not needs_review else "review-required"
    )

    if blocker_codes:
        return OpportunityDecisionProjection(
            schema_version="OpportunityDecisionProjectionV1",
            processing="blocked",
            readiness="blocked",
            pricing="unpriced",
            review=review,
            release="blocked",
            status="blocked",
            recommendation="abstain",
            evidence_receipt_ids=receipts,
            blocker_codes=blocker_codes,
        )
    if is_provisional:
        provisional_codes = tuple(
            code
            for condition, code in (
                (is_thin, "thin-comps"),
                (needs_review, "review-required"),
                (support_is_partial, "support-incomplete"),
            )
            if condition
        )
        return OpportunityDecisionProjection(
            schema_version="OpportunityDecisionProjectionV1",
            processing="complete",
            readiness="provisional",
            pricing="unpriced",
            review=review,
            release="blocked",
            status="provisional",
            recommendation="abstain",
            evidence_receipt_ids=receipts,
            blocker_codes=provisional_codes,
        )
    release: Literal["eligible", "released"] = (
        "released" if decision_input.requested_release else "eligible"
    )
    status: Literal["provisional", "released"] = (
        "released" if decision_input.requested_release else "provisional"
    )
    return OpportunityDecisionProjection(
        schema_version="OpportunityDecisionProjectionV1",
        processing="complete",
        readiness="ready",
        pricing="evidence-supported",
        review="approved",
        release=release,
        status=status,
        recommendation=decision_input.persona.decision_intent,
        verified_ceiling_cents=decision_input.proposed_ceiling_cents,
        evidence_receipt_ids=receipts,
        blocker_codes=(),
    )
