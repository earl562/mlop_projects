from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.contracts import JsonObject
from plotlot.harness.listing_comp_support import (
    contextual_fit_score,
    extract_zip_code,
    extract_municipality_hint,
    extract_lot_size_sqft,
    extract_sale_date,
    extract_sold_price,
    is_sale_date_within_window,
    is_subject_lot_size_similar,
    listing_parse_confidence,
    lot_size_variance_ratio,
    municipality_matches_subject,
    parse_iso_date,
    zip_matches_subject,
)

_SQFT_PER_ACRE = 43_560.0


@dataclass(frozen=True)
class VerifiedListingMetric:
    url: str
    title: str
    address_hint: str
    classification: str
    sale_price: float
    sale_date: str
    lot_size_sqft: float
    lot_size_variance_ratio: float
    fit_score: float
    price_per_acre: float
    confidence: float
    municipality: str | None
    municipality_match: bool
    zip_code: str | None
    zip_match: bool | None
    parsing_confidence: float
    county_reconciliation_required: bool = False
    verification_basis: str = "parsed_listing_facts"


def build_contextual_land_listing_verification(
    *,
    candidates: list[JsonObject],
    fetched_results: list[JsonObject],
    subject_lot_area_sf: float,
    subject_municipality: str = "",
    subject_address: str = "",
    reference_date_iso: str | None = None,
) -> JsonObject:
    if subject_lot_area_sf <= 0:
        return {
            "verified_candidate_count": 0,
            "verified_candidates": [],
        }

    reference_date = parse_iso_date(reference_date_iso) if reference_date_iso else None
    subject_zip_code = extract_zip_code(subject_address)
    results_by_url = {
        str(item.get("url") or "").strip(): item
        for item in fetched_results
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    }
    verified_candidates: list[VerifiedListingMetric] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("classification") or "unknown") != "likely_vacant_land":
            continue
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue
        fetched = results_by_url.get(url)
        if fetched is None:
            continue
        raw_text = " ".join(
            [
                str(candidate.get("title") or ""),
                str(candidate.get("description") or ""),
                str(fetched.get("description") or ""),
                str(fetched.get("content") or ""),
            ]
        ).strip()
        sale_price = extract_sold_price(raw_text)
        sale_date = extract_sale_date(
            raw_text,
            fallback_values=(
                candidate.get("sale_date"),
                fetched.get("sale_date"),
            ),
        )
        candidate_municipality = extract_municipality_hint(
            candidate.get("address_hint"),
            candidate.get("title"),
            raw_text,
        )
        candidate_zip_code = extract_zip_code(
            candidate.get("address_hint"),
            candidate.get("title"),
            raw_text,
        )
        if not municipality_matches_subject(
            subject_municipality=subject_municipality,
            candidate_municipality=candidate_municipality,
        ):
            continue
        lot_size_sqft = extract_lot_size_sqft(raw_text)
        if sale_price is None or sale_date is None or lot_size_sqft is None or lot_size_sqft <= 0:
            address_hint = str(candidate.get("address_hint") or "").strip()
            if not address_hint:
                continue
            verified_candidates.append(
                VerifiedListingMetric(
                    url=url,
                    title=str(candidate.get("title") or fetched.get("title") or url),
                    address_hint=address_hint,
                    classification="likely_vacant_land",
                    sale_price=0.0,
                    sale_date="",
                    lot_size_sqft=0.0,
                    lot_size_variance_ratio=float(candidate.get("lot_size_variance_ratio") or 1.0),
                    fit_score=float(candidate.get("fit_score") or 0.0),
                    price_per_acre=0.0,
                    confidence=min(float(candidate.get("confidence") or 0.35), 0.45),
                    municipality=candidate_municipality,
                    municipality_match=True,
                    zip_code=candidate_zip_code,
                    zip_match=zip_matches_subject(
                        subject_zip_code=subject_zip_code,
                        candidate_zip_code=candidate_zip_code,
                    ),
                    parsing_confidence=0.2,
                    county_reconciliation_required=True,
                    verification_basis="address_only_public_listing",
                )
            )
            continue
        if not is_subject_lot_size_similar(
            subject_lot_area_sf=subject_lot_area_sf,
            comparable_lot_size_sqft=lot_size_sqft,
        ):
            continue
        if not is_sale_date_within_window(
            sale_date=sale_date,
            search_window_months=candidate.get("search_window_months"),
            reference_date=reference_date,
        ):
            continue
        size_variance_ratio = lot_size_variance_ratio(
            subject_lot_area_sf=subject_lot_area_sf,
            comparable_lot_size_sqft=lot_size_sqft,
        )
        if size_variance_ratio is None:
            continue
        verified_candidates.append(
            VerifiedListingMetric(
                url=url,
                title=str(candidate.get("title") or fetched.get("title") or url),
                address_hint=str(candidate.get("address_hint") or ""),
                classification="likely_vacant_land",
                sale_price=sale_price,
                sale_date=sale_date,
                lot_size_sqft=lot_size_sqft,
                lot_size_variance_ratio=round(size_variance_ratio, 3),
                fit_score=contextual_fit_score(
                    subject_lot_area_sf=subject_lot_area_sf,
                    comparable_lot_size_sqft=lot_size_sqft,
                ),
                price_per_acre=round(sale_price / (lot_size_sqft / _SQFT_PER_ACRE), 2),
                confidence=0.55,
                municipality=candidate_municipality,
                municipality_match=True,
                zip_code=candidate_zip_code,
                zip_match=zip_matches_subject(
                    subject_zip_code=subject_zip_code,
                    candidate_zip_code=candidate_zip_code,
                ),
                parsing_confidence=listing_parse_confidence(
                    sale_price=sale_price,
                    sale_date=sale_date,
                    lot_size_sqft=lot_size_sqft,
                    municipality=candidate_municipality,
                    zip_code=candidate_zip_code,
                ),
            )
        )

    verified_candidates.sort(
        key=lambda metric: (
            metric.zip_match is not True,
            -metric.fit_score,
            metric.lot_size_variance_ratio,
            -metric.confidence,
            metric.address_hint,
        )
    )
    reconciliation_candidates = [
        metric for metric in verified_candidates if metric.county_reconciliation_required
    ]
    verified_candidates = [
        metric for metric in verified_candidates if not metric.county_reconciliation_required
    ]
    price_per_acre_values = sorted(
        metric.price_per_acre for metric in verified_candidates if metric.price_per_acre > 0
    )
    low_ppa, median_ppa, high_ppa = _price_range(price_per_acre_values)
    subject_acres = subject_lot_area_sf / _SQFT_PER_ACRE
    return {
        "verified_candidate_count": len(verified_candidates),
        "verified_candidates": [_metric_payload(metric) for metric in verified_candidates],
        "reconciliation_candidate_count": len(reconciliation_candidates),
        "reconciliation_candidates": [
            _metric_payload(metric) for metric in reconciliation_candidates
        ],
        "price_per_acre_low": low_ppa,
        "price_per_acre_median": median_ppa,
        "price_per_acre_high": high_ppa,
        "estimated_land_value_low": round(low_ppa * subject_acres, 2) if low_ppa > 0 else 0.0,
        "estimated_land_value": round(median_ppa * subject_acres, 2) if median_ppa > 0 else 0.0,
        "estimated_land_value_high": round(high_ppa * subject_acres, 2) if high_ppa > 0 else 0.0,
    }


def _metric_payload(metric: VerifiedListingMetric) -> JsonObject:
    return {
        "url": metric.url,
        "title": metric.title,
        "address_hint": metric.address_hint,
        "classification": metric.classification,
        "sale_price": metric.sale_price,
        "sale_date": metric.sale_date,
        "lot_size_sqft": metric.lot_size_sqft,
        "lot_size_variance_ratio": metric.lot_size_variance_ratio,
        "fit_score": metric.fit_score,
        "price_per_acre": metric.price_per_acre,
        "confidence": metric.confidence,
        "municipality": metric.municipality,
        "municipality_match": metric.municipality_match,
        "zip_code": metric.zip_code,
        "zip_match": metric.zip_match,
        "parsing_confidence": metric.parsing_confidence,
        "county_reconciliation_required": metric.county_reconciliation_required,
        "verification_basis": metric.verification_basis,
    }


def _price_range(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        value = round(values[0], 2)
        return value, value, value
    return (
        _percentile(values, 25.0),
        _percentile(values, 50.0),
        _percentile(values, 75.0),
    )


def _percentile(sorted_values: list[float], pct: float) -> float:
    position = (len(sorted_values) - 1) * (pct / 100.0)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    if lower_index == upper_index:
        return round(lower_value, 2)
    fraction = position - lower_index
    return round(lower_value * (1 - fraction) + upper_value * fraction, 2)
