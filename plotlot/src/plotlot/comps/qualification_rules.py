from dataclasses import dataclass
from datetime import date, datetime
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Final, assert_never

from plotlot.comps.dates import DateWindow, assess_sale_date
from plotlot.comps.models import CompPolicy, CompSubject, SaleEvidence

_EARTH_RADIUS_MILES: Final = 3958.7613
_SQFT_PER_ACRE: Final = 43_560.0
_EXPLICIT_NON_MARKET_CODES: Final = frozenset({"gift"})


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    distance_miles: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComparabilityContext:
    subject: CompSubject
    policy: CompPolicy
    distance_miles: float | None


def _normalized_identity(value: str) -> str:
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    return normalized.lstrip("0") or normalized


def _same_jurisdiction(subject: CompSubject, candidate: SaleEvidence) -> bool:
    return (
        subject.state.strip().casefold() == candidate.state.strip().casefold()
        and subject.county.strip().casefold() == candidate.county.strip().casefold()
    )


def _distance_miles(subject: CompSubject, candidate: SaleEvidence) -> float | None:
    if (
        subject.latitude is None
        or subject.longitude is None
        or candidate.latitude is None
        or candidate.longitude is None
    ):
        return None
    subject_latitude = radians(subject.latitude)
    candidate_latitude = radians(candidate.latitude)
    latitude_delta = candidate_latitude - subject_latitude
    longitude_delta = radians(candidate.longitude - subject.longitude)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(subject_latitude) * cos(candidate_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_MILES * asin(sqrt(haversine))


def _review_date_is_valid(value: str) -> bool:
    if not value.strip():
        return False
    normalized = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def _source_reasons(candidate: SaleEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    match candidate.source_kind:
        case "county":
            if not candidate.source_url.strip():
                reasons.append("missing_source_url")
            if not candidate.qualification_code.strip():
                reasons.append("missing_qualification_code")
            if not candidate.source_record_id.strip() and not candidate.recorded_document.strip():
                reasons.append("missing_record_reference")
            if not candidate.classification_basis.strip():
                reasons.append("missing_classification_basis")
        case "recorder":
            if not candidate.source_url.strip():
                reasons.append("missing_source_url")
            if not candidate.source_record_id.strip() and not candidate.recorded_document.strip():
                reasons.append("missing_record_reference")
            if not candidate.classification_basis.strip():
                reasons.append("missing_classification_basis")
        case "user_reviewed":
            if (
                not candidate.source_url.strip()
                and not candidate.source_record_id.strip()
                and not candidate.recorded_document.strip()
            ):
                reasons.append("missing_source_reference")
            if not candidate.classification_basis.strip():
                reasons.append("missing_classification_basis")
            if not candidate.reviewed_by.strip() or not _review_date_is_valid(
                candidate.reviewed_at
            ):
                reasons.append("missing_or_invalid_review_attestation")
        case "listing" | "unknown":
            reasons.append("unsupported_source_kind")
        case source_unreachable:
            assert_never(source_unreachable)
    return tuple(reasons)


def _comparability_reasons(
    context: ComparabilityContext, candidate: SaleEvidence
) -> tuple[str, ...]:
    reasons: list[str] = []
    subject = context.subject
    policy = context.policy
    if candidate.category != subject.category:
        reasons.append("category_mismatch")
    if candidate.property_type != subject.property_type:
        reasons.append("property_type_mismatch")
    if context.distance_miles is None:
        reasons.append("missing_coordinates")
    elif context.distance_miles > policy.radius_miles:
        reasons.append("outside_radius")
    match subject.category:
        case "land":
            if subject.property_type != "land":
                reasons.append("missing_subject_property_type")
            if subject.lot_size_sqft is None:
                reasons.append("missing_subject_lot_size")
            if candidate.lot_size_sqft is None:
                reasons.append("missing_lot_size")
            if subject.lot_size_sqft is not None and candidate.lot_size_sqft is not None:
                ratio = candidate.lot_size_sqft / subject.lot_size_sqft
                if abs(ratio - 1) > policy.size_tolerance:
                    reasons.append("size_outside_tolerance")
            if candidate.sale_price is not None and candidate.lot_size_sqft is not None:
                normalized_value = candidate.sale_price / candidate.lot_size_sqft * _SQFT_PER_ACRE
                if not isfinite(normalized_value):
                    reasons.append("non_finite_derived_value")
        case "resale" | "new_construction":
            if subject.property_type in {"land", "unknown"}:
                reasons.append("missing_subject_property_type")
            if subject.building_area_sqft is None:
                reasons.append("missing_subject_building_area")
            if candidate.building_area_sqft is None:
                reasons.append("missing_building_area")
            if candidate.units is None:
                reasons.append("missing_units")
            if subject.building_area_sqft is not None and candidate.building_area_sqft is not None:
                ratio = candidate.building_area_sqft / subject.building_area_sqft
                if abs(ratio - 1) > policy.size_tolerance:
                    reasons.append("size_outside_tolerance")
        case "incomplete" | "unknown":
            reasons.append("unsupported_category")
        case subject_category_unreachable:
            assert_never(subject_category_unreachable)
    if (
        subject.zoning_code
        and candidate.zoning_code
        and subject.zoning_code != candidate.zoning_code
    ):
        reasons.append("zoning_mismatch")
    if (
        subject.neighborhood
        and candidate.neighborhood
        and subject.neighborhood.casefold() != candidate.neighborhood.casefold()
    ):
        reasons.append("neighborhood_mismatch")
    if (
        subject.waterfront is not None
        and candidate.waterfront is not None
        and subject.waterfront != candidate.waterfront
    ):
        reasons.append("waterfront_mismatch")
    return tuple(reasons)


def assess_candidate(
    subject: CompSubject, candidate: SaleEvidence, policy: CompPolicy
) -> CandidateAssessment:
    reasons: list[str] = []
    distance = _distance_miles(subject, candidate)
    if not candidate.parcel_id.strip():
        reasons.append("missing_parcel_id")
    elif _normalized_identity(candidate.parcel_id) == _normalized_identity(subject.parcel_id):
        reasons.append("subject_transaction")
    if candidate.sale_price is None or candidate.sale_price <= 0:
        reasons.append("invalid_sale_price")
    sale_date = assess_sale_date(
        candidate.sale_date,
        candidate.date_precision,
        DateWindow(date.fromisoformat(policy.as_of), policy.months),
    )
    if sale_date.reason is not None:
        reasons.append(sale_date.reason)
    if not _same_jurisdiction(subject, candidate):
        reasons.append("jurisdiction_mismatch")
    match candidate.transaction_status:
        case "closed":
            pass
        case "active" | "pending" | "unknown":
            reasons.append("transaction_not_closed")
        case transaction_unreachable:
            assert_never(transaction_unreachable)
    match candidate.qualification:
        case "qualified":
            pass
        case "disqualified" | "pending" | "unknown":
            reasons.append("qualification_not_qualified")
        case qualification_unreachable:
            assert_never(qualification_unreachable)
    if candidate.qualification_code.strip().casefold() in _EXPLICIT_NON_MARKET_CODES:
        reasons.append("non_market_transfer")
    if candidate.multi_parcel:
        reasons.append("multi_parcel_transaction")
    if candidate.property_changed:
        reasons.append("property_changed_since_sale")
    if candidate.conflict_flags:
        reasons.append("evidence_conflict")
    reasons.extend(_source_reasons(candidate))
    context = ComparabilityContext(subject, policy, distance)
    reasons.extend(_comparability_reasons(context, candidate))
    match candidate.category:
        case "new_construction":
            if not candidate.construction_completed_date.strip():
                reasons.append("missing_construction_completion_date")
            if not candidate.completion_source.strip():
                reasons.append("missing_completion_source")
            if candidate.construction_completed_date.strip() and sale_date.value is not None:
                try:
                    completion_date = date.fromisoformat(
                        candidate.construction_completed_date.strip()
                    )
                except ValueError:
                    reasons.append("invalid_construction_completion_date")
                else:
                    if (
                        len(candidate.construction_completed_date.strip()) != 10
                        or completion_date.isoformat()
                        != candidate.construction_completed_date.strip()
                    ):
                        reasons.append("invalid_construction_completion_date")
                    elif completion_date >= sale_date.value.start:
                        reasons.append("construction_not_completed_before_sale")
        case "land" | "resale" | "incomplete" | "unknown":
            pass
        case candidate_category_unreachable:
            assert_never(candidate_category_unreachable)
    return CandidateAssessment(distance, tuple(reasons))
