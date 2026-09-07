from collections.abc import Sequence
from dataclasses import replace
from typing import Final, assert_never

from plotlot.comps.dates import evidence_date_sort_key
from plotlot.comps.models import (
    POLICY_VERSION,
    CompCategory,
    CompDecision,
    CompPolicy,
    CompSetResult,
    CompSubject,
    SaleEvidence,
)
from plotlot.comps.qualification_rules import CandidateAssessment, assess_candidate
from plotlot.comps.reconciliation import (
    block_duplicate_evidence_ids,
    block_duplicate_transactions,
    limit_one_sale_per_parcel,
)

_SQFT_PER_ACRE: Final = 43_560.0


def _decision(candidate: SaleEvidence, assessment: CandidateAssessment) -> CompDecision:
    return CompDecision(
        evidence_id=candidate.evidence_id,
        parcel_id=candidate.parcel_id,
        state=candidate.state,
        county=candidate.county,
        address=candidate.address,
        sale_price=candidate.sale_price,
        sale_date=candidate.sale_date,
        date_precision=candidate.date_precision,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        lot_size_sqft=candidate.lot_size_sqft,
        building_area_sqft=candidate.building_area_sqft,
        units=candidate.units,
        property_type=candidate.property_type,
        category=candidate.category,
        classification_basis=candidate.classification_basis,
        transaction_status=candidate.transaction_status,
        qualification=candidate.qualification,
        qualification_code=candidate.qualification_code,
        source_kind=candidate.source_kind,
        source_url=candidate.source_url,
        source_record_id=candidate.source_record_id,
        recorded_document=candidate.recorded_document,
        retrieved_at=candidate.retrieved_at,
        reviewed_by=candidate.reviewed_by,
        reviewed_at=candidate.reviewed_at,
        review_notes=candidate.review_notes,
        multi_parcel=candidate.multi_parcel,
        property_changed=candidate.property_changed,
        conflict_flags=candidate.conflict_flags,
        construction_completed_date=candidate.construction_completed_date,
        completion_source=candidate.completion_source,
        zoning_code=candidate.zoning_code,
        neighborhood=candidate.neighborhood,
        waterfront=candidate.waterfront,
        distance_miles=(
            round(assessment.distance_miles, 6) if assessment.distance_miles is not None else None
        ),
        reasons=assessment.reasons,
        accepted=not assessment.reasons,
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return round(ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction, 2)


def _value_basis(category: CompCategory) -> str:
    match category:
        case "land":
            return "price_per_acre"
        case "resale" | "new_construction":
            return "price_per_unit"
        case "incomplete" | "unknown":
            return ""
        case unreachable:
            assert_never(unreachable)


def _comp_value(decision: CompDecision, category: CompCategory) -> float | None:
    if decision.sale_price is None:
        return None
    match category:
        case "land":
            if decision.lot_size_sqft is None:
                return None
            return decision.sale_price / decision.lot_size_sqft * _SQFT_PER_ACRE
        case "resale" | "new_construction":
            if decision.units is None:
                return None
            return decision.sale_price / decision.units
        case "incomplete" | "unknown":
            return None
        case unreachable:
            assert_never(unreachable)


def qualify_comps(
    subject: CompSubject, candidates: Sequence[SaleEvidence], policy: CompPolicy
) -> CompSetResult:
    initial = tuple(assess_candidate(subject, candidate, policy) for candidate in candidates)
    unique_ids = block_duplicate_evidence_ids(candidates, initial)
    deduplicated = block_duplicate_transactions(candidates, unique_ids)
    assessments = limit_one_sale_per_parcel(candidates, deduplicated)
    decisions = tuple(
        _decision(candidate, assessment)
        for candidate, assessment in zip(candidates, assessments, strict=True)
    )
    eligible_indices = sorted(
        (index for index, decision in enumerate(decisions) if decision.accepted),
        key=lambda index: (
            assessments[index].distance_miles
            if assessments[index].distance_miles is not None
            else float("inf"),
            -evidence_date_sort_key(decisions[index].sale_date, decisions[index].date_precision),
            decisions[index].evidence_id,
        ),
    )
    selected_indices = set(eligible_indices[: policy.max_comps])
    final_decisions = tuple(
        replace(decision, reasons=("not_selected",), accepted=False)
        if decision.accepted and index not in selected_indices
        else decision
        for index, decision in enumerate(decisions)
    )
    accepted = tuple(
        final_decisions[index] for index in eligible_indices if index in selected_indices
    )
    rejected = tuple(decision for decision in final_decisions if not decision.accepted)
    sufficient = len(accepted) >= policy.min_comps
    values = tuple(
        value
        for decision in accepted
        if (value := _comp_value(decision, subject.category)) is not None
    )
    notes = (
        () if sufficient else (f"{len(accepted)} qualifying comps; {policy.min_comps} required",)
    )
    return CompSetResult(
        status="qualified" if sufficient else "insufficient_evidence",
        category=subject.category,
        policy_version=POLICY_VERSION,
        as_of=policy.as_of,
        accepted=accepted,
        rejected=rejected,
        candidate_count=len(candidates),
        value_low=_percentile(values, 0.25) if sufficient else None,
        value_median=_percentile(values, 0.5) if sufficient else None,
        value_high=_percentile(values, 0.75) if sufficient else None,
        value_basis=_value_basis(subject.category),
        notes=notes,
    )
