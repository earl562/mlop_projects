"""Deterministic qualification and valuation for comparable property sales."""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Sequence
from datetime import date

from plotlot.application.market.models import (
    ComparableSale,
    CompConfidence,
    CompPolicy,
    CompSetResult,
    CompStatus,
    ExcludedComparable,
    ExclusionReason,
    QualifiedComparable,
    SubjectProperty,
    ValuationBasis,
)

_EARTH_RADIUS_MILES = 3_958.7613
_PROPERTY_TYPE_ALIASES = {
    "apartment": "multifamily",
    "apartments": "multifamily",
    "multi family": "multifamily",
    "multifamily residential": "multifamily",
    "residential land": "land",
    "vacant land": "land",
    "lot": "land",
    "lots": "land",
}


def _normalize_address(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _normalize_property_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[_-]+", " ", value.casefold()).strip()
    return _PROPERTY_TYPE_ALIASES.get(normalized, normalized.replace(" ", "_"))


def _distance_miles(subject: SubjectProperty, sale: ComparableSale) -> float | None:
    coordinates = (
        subject.latitude,
        subject.longitude,
        sale.latitude,
        sale.longitude,
    )
    if any(value is None for value in coordinates):
        return None

    subject_lat = math.radians(float(subject.latitude))
    sale_lat = math.radians(float(sale.latitude))
    latitude_delta = math.radians(float(sale.latitude) - float(subject.latitude))
    longitude_delta = math.radians(float(sale.longitude) - float(subject.longitude))
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(subject_lat)
        * math.cos(sale_lat)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(value))


def _source_key(sale: ComparableSale) -> tuple[str, str] | None:
    source = sale.source
    if source is None:
        return None
    if not source.provider or not source.record_id or not source.source_url:
        return None
    return source.provider.casefold(), source.record_id.casefold()


def _outside_ratio(
    subject_value: float | None,
    candidate_value: float | None,
    *,
    minimum: float,
    maximum: float,
) -> bool:
    if subject_value is None or candidate_value is None:
        return False
    ratio = candidate_value / subject_value
    return not minimum <= ratio <= maximum


def _select_valuation_basis(
    subject: SubjectProperty,
    candidates: Sequence[tuple[ComparableSale, float | None, int]],
) -> tuple[ValuationBasis, float, list[float]]:
    if subject.building_sqft and all(
        sale.building_sqft for sale, _distance, _age in candidates
    ):
        return (
            "building_sqft",
            subject.building_sqft,
            [
                sale.sale_price / float(sale.building_sqft)
                for sale, _distance, _age in candidates
            ],
        )
    if subject.lot_size_sqft and all(
        sale.lot_size_sqft for sale, _distance, _age in candidates
    ):
        return (
            "lot_sqft",
            subject.lot_size_sqft,
            [
                sale.sale_price / float(sale.lot_size_sqft)
                for sale, _distance, _age in candidates
            ],
        )
    return "sale_price", 1.0, [
        sale.sale_price for sale, _distance, _age in candidates
    ]


def _is_outlier(
    value: float,
    values: Sequence[float],
    *,
    modified_z_threshold: float,
) -> bool:
    if len(values) < 4:
        return False

    median = statistics.median(values)
    deviations = [abs(item - median) for item in values]
    median_absolute_deviation = statistics.median(deviations)
    if median_absolute_deviation > 0:
        modified_z = 0.6745 * (value - median) / median_absolute_deviation
        return abs(modified_z) > modified_z_threshold

    if median <= 0:
        return False
    ratio = value / median
    return ratio < 0.5 or ratio > 2.0


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _confidence(qualified: Sequence[QualifiedComparable]) -> CompConfidence:
    score = 0
    if len(qualified) >= 6:
        score += 2
    elif len(qualified) >= 4:
        score += 1

    if statistics.median(item.age_days for item in qualified) <= 365:
        score += 1

    distances = [
        item.distance_miles
        for item in qualified
        if item.distance_miles is not None
    ]
    if distances and statistics.median(distances) <= 1:
        score += 1

    providers = {
        item.sale.source.provider.casefold()
        for item in qualified
        if item.sale.source is not None
    }
    if len(providers) >= 2:
        score += 1

    if score >= 4:
        return CompConfidence.HIGH
    if score >= 2:
        return CompConfidence.MEDIUM
    return CompConfidence.LOW


def qualify_comps(
    subject: SubjectProperty,
    sales: Sequence[ComparableSale],
    policy: CompPolicy,
    *,
    as_of: date | None = None,
) -> CompSetResult:
    """Filter, normalize, and value comparable sales without model judgment."""

    effective_date = as_of or date.today()
    subject_address = _normalize_address(subject.address)
    subject_type = _normalize_property_type(subject.property_type)
    seen_sources: set[tuple[str, str]] = set()
    excluded: list[ExcludedComparable] = []
    candidates: list[tuple[ComparableSale, float | None, int]] = []

    for sale in sales:
        reasons: list[ExclusionReason] = []
        if _normalize_address(sale.address) == subject_address:
            reasons.append(ExclusionReason.SUBJECT_PROPERTY)

        source_key = _source_key(sale)
        if source_key is None:
            reasons.append(ExclusionReason.MISSING_PROVENANCE)
        elif source_key in seen_sources:
            reasons.append(ExclusionReason.DUPLICATE)
        else:
            seen_sources.add(source_key)

        age_days = (effective_date - sale.sale_date).days
        if age_days < 0 or age_days > policy.max_age_days:
            reasons.append(ExclusionReason.STALE)

        distance = _distance_miles(subject, sale)
        if distance is not None and distance > policy.max_distance_miles:
            reasons.append(ExclusionReason.OUTSIDE_RADIUS)

        sale_type = _normalize_property_type(sale.property_type)
        if subject_type and sale_type and sale_type != subject_type:
            reasons.append(ExclusionReason.PROPERTY_TYPE_MISMATCH)

        if _outside_ratio(
            subject.lot_size_sqft,
            sale.lot_size_sqft,
            minimum=policy.min_lot_size_ratio,
            maximum=policy.max_lot_size_ratio,
        ):
            reasons.append(ExclusionReason.LOT_SIZE_MISMATCH)

        if _outside_ratio(
            subject.building_sqft,
            sale.building_sqft,
            minimum=policy.min_building_size_ratio,
            maximum=policy.max_building_size_ratio,
        ):
            reasons.append(ExclusionReason.BUILDING_SIZE_MISMATCH)

        if reasons:
            excluded.append(
                ExcludedComparable(
                    sale_id=sale.sale_id,
                    address=sale.address,
                    reasons=tuple(dict.fromkeys(reasons)),
                )
            )
            continue

        candidates.append((sale, distance, age_days))

    basis, subject_multiplier, normalized_values = _select_valuation_basis(
        subject,
        candidates,
    )
    qualified: list[QualifiedComparable] = []
    for candidate, normalized_price in zip(
        candidates,
        normalized_values,
        strict=True,
    ):
        sale, distance, age_days = candidate
        if _is_outlier(
            normalized_price,
            normalized_values,
            modified_z_threshold=policy.outlier_modified_z,
        ):
            excluded.append(
                ExcludedComparable(
                    sale_id=sale.sale_id,
                    address=sale.address,
                    reasons=(ExclusionReason.PRICE_OUTLIER,),
                )
            )
            continue
        qualified.append(
            QualifiedComparable(
                sale=sale,
                distance_miles=distance,
                age_days=age_days,
                normalized_price=normalized_price,
            )
        )

    evidence_ids = tuple(
        item.sale.evidence_id for item in qualified if item.sale.evidence_id
    )
    if len(qualified) < policy.min_comps:
        return CompSetResult(
            status=CompStatus.INSUFFICIENT_EVIDENCE,
            confidence=CompConfidence.INSUFFICIENT,
            qualified=tuple(qualified),
            excluded=tuple(excluded),
            valuation_basis=basis,
            evidence_ids=evidence_ids,
            message=(
                f"At least {policy.min_comps} qualified comparable sales are required; "
                f"found {len(qualified)}."
            ),
        )

    values = [item.normalized_price for item in qualified]
    valuation_low = _percentile(values, 0.25) * subject_multiplier
    valuation_median = _percentile(values, 0.5) * subject_multiplier
    valuation_high = _percentile(values, 0.75) * subject_multiplier

    return CompSetResult(
        status=CompStatus.QUALIFIED,
        confidence=_confidence(qualified),
        qualified=tuple(qualified),
        excluded=tuple(excluded),
        valuation_basis=basis,
        valuation_low=round(valuation_low, 2),
        valuation_median=round(valuation_median, 2),
        valuation_high=round(valuation_high, 2),
        evidence_ids=evidence_ids,
        message=(
            f"{len(qualified)} qualified comparable sales support the valuation range."
        ),
    )


__all__ = ["qualify_comps"]
