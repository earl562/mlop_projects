from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.comparable_listing_candidates import (
    candidate_confidence as candidate_confidence,
    candidate_dedupe_key as candidate_dedupe_key,
    candidate_sort_key as candidate_sort_key,
    classify_listing_candidate as classify_listing_candidate,
    listing_query_should_stop as listing_query_should_stop,
    locality_score as locality_score,
    normalize_listing_candidates as normalize_listing_candidates,
    rank_listing_candidates as rank_listing_candidates,
)
from plotlot.harness.contracts import JsonObject
from plotlot.harness.listing_comp_support import extract_zip_code


@dataclass(frozen=True, slots=True)
class ComparableListingQuery:
    query: str
    search_category: str
    window_months: int
    purpose: str
    stop_rule: str


def build_comparable_listing_queries(subject_payload: JsonObject) -> list[ComparableListingQuery]:
    address = _clean(subject_payload.get("address"))
    municipality = _clean(subject_payload.get("municipality"))
    county = _clean(subject_payload.get("county"))
    zip_code = extract_zip_code(address)
    location_terms = _listing_market_area_terms(
        address=address,
        municipality=municipality,
        county=county,
        zip_code=zip_code,
    )
    domain_fragment = "site:zillow.com OR site:redfin.com"
    return [
        ComparableListingQuery(
            query=(
                f"{location_terms} sold vacant land lot comps last 6 months {domain_fragment}"
            ).strip(),
            search_category="sold_land",
            window_months=6,
            purpose="primary_recent_land_comp_search",
            stop_rule="continue_until_two_local_land_candidates_or_expand_window",
        ),
        ComparableListingQuery(
            query=(
                f"{location_terms} sold vacant land lot comps last 12 months {domain_fragment}"
            ).strip(),
            search_category="sold_land",
            window_months=12,
            purpose="expanded_recent_land_comp_search",
            stop_rule="continue_until_two_local_land_candidates_or_expand_window",
        ),
        ComparableListingQuery(
            query=(
                f"{location_terms} sold vacant land lot comps last 24 months {domain_fragment}"
            ).strip(),
            search_category="sold_land",
            window_months=24,
            purpose="maximum_land_comp_lookback_search",
            stop_rule="continue_to_improved_sale_fallback_if_land_support_is_thin",
        ),
        ComparableListingQuery(
            query=(
                f"{location_terms} sold new construction house comps last 12 months {domain_fragment}"
            ).strip(),
            search_category="new_build_houses",
            window_months=12,
            purpose="exit_value_new_build_fallback_search",
            stop_rule="stop_after_one_local_improved_sale_candidate",
        ),
        ComparableListingQuery(
            query=(
                f"{location_terms} sold renovated house comps last 12 months {domain_fragment}"
            ).strip(),
            search_category="renovated_houses",
            window_months=12,
            purpose="exit_value_renovated_sale_fallback_search",
            stop_rule="stop_after_one_local_improved_sale_candidate",
        ),
    ]


def comparable_listing_query_plan(subject_payload: JsonObject) -> list[JsonObject]:
    return [
        {
            "step": index,
            "purpose": query.purpose,
            "search_category": query.search_category,
            "search_window_months": query.window_months,
            "query": query.query,
            "stop_rule": query.stop_rule,
        }
        for index, query in enumerate(build_comparable_listing_queries(subject_payload), start=1)
    ]


def _clean(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _listing_market_area_terms(
    *,
    address: str,
    municipality: str,
    county: str,
    zip_code: str | None,
) -> str:
    if not municipality and not county:
        return address
    broad_terms = [part for part in (municipality, county, zip_code or "") if part]
    if broad_terms:
        return " ".join(broad_terms)
    return address
