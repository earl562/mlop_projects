from __future__ import annotations

from datetime import date, datetime, timezone

from plotlot.harness.contracts import JsonObject
from plotlot.harness.listing_comp_support import extract_zip_code, parse_iso_date, zip_matches_subject


def best_exit_comp_snapshot(
    *,
    unit_comparables: list[JsonObject],
    adv_per_unit: float,
    subject_address: str = "",
) -> JsonObject:
    subject_zip_code = extract_zip_code(subject_address)
    ranked = [
        _exit_comp_snapshot(
            comparable=comparable,
            adv_per_unit=adv_per_unit,
            subject_zip_code=subject_zip_code,
        )
        for comparable in unit_comparables
        if isinstance(comparable, dict)
    ]
    ranked = [snapshot for snapshot in ranked if snapshot]
    if not ranked:
        return {}
    ranked.sort(
        key=lambda snapshot: (
            _locality_rank(str(snapshot["market_scope"])),
            -float(snapshot["qualification_score"]),
            -float(snapshot["fit_score"]),
            -int(snapshot["sale_timestamp"]),
            float(snapshot["distance_miles"]),
            str(snapshot["address"]),
        )
    )
    best_snapshot = ranked[0]
    return {
        "exit_support_distance_miles": float(best_snapshot["distance_miles"]),
        "exit_support_market_scope": str(best_snapshot["market_scope"]),
        "exit_support_zip_match": best_snapshot["zip_match"],
        "exit_support_sale_date": str(best_snapshot["sale_date"]),
        "exit_support_recency_tier": str(best_snapshot["recency_tier"]),
    }


def _exit_comp_snapshot(
    *,
    comparable: JsonObject,
    adv_per_unit: float,
    subject_zip_code: str | None,
) -> JsonObject:
    price_per_unit = comparable.get("price_per_unit")
    if not isinstance(price_per_unit, int | float) or float(price_per_unit) <= 0:
        return {}
    sale_date = str(comparable.get("sale_date") or "").strip()
    parsed_sale_date = parse_iso_date(sale_date)
    candidate_zip_code = _candidate_zip_code(comparable)
    zip_match = zip_matches_subject(
        subject_zip_code=subject_zip_code,
        candidate_zip_code=candidate_zip_code,
    )
    return {
        "address": str(comparable.get("address") or "").strip(),
        "distance_miles": _float_value(comparable.get("distance_miles")),
        "fit_score": _exit_fit_score(
            price_per_unit=float(price_per_unit),
            adv_per_unit=adv_per_unit,
        ),
        "market_scope": _exit_market_scope(comparable, zip_match),
        "qualification_score": _qualification_score(comparable),
        "recency_tier": _recency_tier(parsed_sale_date),
        "sale_date": sale_date,
        "sale_timestamp": _sale_timestamp(parsed_sale_date),
        "zip_match": zip_match,
    }


def _exit_fit_score(*, price_per_unit: float, adv_per_unit: float) -> float:
    if adv_per_unit <= 0:
        return 0.0
    variance_ratio = abs(price_per_unit - adv_per_unit) / adv_per_unit
    return round(max(0.0, 1.0 - variance_ratio), 3)


def _qualification_score(comparable: JsonObject) -> float:
    adjustments = comparable.get("adjustments")
    if not isinstance(adjustments, dict):
        return 0.0
    qualification_score = adjustments.get("qualification_score")
    if not isinstance(qualification_score, int | float):
        return 0.0
    return float(qualification_score)


def _exit_market_scope(comparable: JsonObject, zip_match: bool | None) -> str:
    adjustments = comparable.get("adjustments")
    if not isinstance(adjustments, dict):
        return _market_scope_from_zip_match(zip_match)
    if adjustments.get("municipality_mismatch") == 1.0:
        return "outside_subject_municipality"
    if adjustments.get("municipality_unknown") == 1.0:
        return "unknown"
    return _market_scope_from_zip_match(zip_match)


def _market_scope_from_zip_match(zip_match: bool | None) -> str:
    match zip_match:
        case True:
            return "subject_zip"
        case False:
            return "cross_zip_same_municipality"
        case None:
            return "subject_municipality"


def _candidate_zip_code(comparable: JsonObject) -> str | None:
    raw_zip_code = comparable.get("zip_code")
    if isinstance(raw_zip_code, str) and raw_zip_code.strip():
        return raw_zip_code.strip()
    return extract_zip_code(str(comparable.get("address") or "").strip())


def _locality_rank(market_scope: str) -> int:
    match market_scope:
        case "subject_zip":
            return 0
        case "subject_municipality":
            return 1
        case "cross_zip_same_municipality":
            return 2
        case "outside_subject_municipality":
            return 3
        case _:
            return 4


def _recency_tier(parsed_sale_date: date | None) -> str:
    if not isinstance(parsed_sale_date, date):
        return "unknown"
    days_since_sale = (datetime.now(timezone.utc).date() - parsed_sale_date).days
    if days_since_sale <= 183:
        return "recent_6m"
    if days_since_sale <= 366:
        return "recent_12m"
    if days_since_sale <= 731:
        return "extended_24m"
    return "stale"


def _sale_timestamp(parsed_sale_date: date | None) -> int:
    if not isinstance(parsed_sale_date, date):
        return 0
    return parsed_sale_date.toordinal()


def _float_value(value: object) -> float:
    if not isinstance(value, int | float):
        return 0.0
    return float(value)
