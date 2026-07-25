from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse

from plotlot.harness.contracts import JsonObject
from plotlot.harness.listing_comp_support import (
    extract_lot_size_sqft,
    extract_municipality_hint,
    extract_sold_price,
    extract_zip_code,
    municipality_matches_subject,
    zip_matches_subject,
)

_ALLOWED_LISTING_DOMAINS = frozenset({"www.zillow.com", "zillow.com", "www.redfin.com", "redfin.com"})
_LAND_LISTING_KEYWORDS = (
    "vacant land",
    "vacant lot",
    "sold land",
    "sold lot",
    "land for sale",
    "lot for sale",
    "residential lot",
    "buildable lot",
    "vacant residential",
    "undeveloped",
    "raw land",
)
_IMPROVED_LISTING_KEYWORDS = (
    "single family",
    "singlefamily",
    "single family residence",
    "residence",
    "beds",
    "baths",
    "sqft",
    "built in",
    "zestimate",
    "estimated rent",
    "home details",
    "new construction",
    "renovated",
    "updated home",
)


class ListingQuery(Protocol):
    query: str
    search_category: str
    window_months: int


def normalize_listing_candidates(
    raw_results: list[JsonObject],
    *,
    query: ListingQuery,
    subject_payload: JsonObject,
) -> list[JsonObject]:
    subject_address = _clean(subject_payload.get("address"))
    subject_municipality = _clean(subject_payload.get("municipality"))
    subject_zip_code = extract_zip_code(subject_address)
    normalized: list[JsonObject] = []
    for raw_result in raw_results:
        title = _clean(raw_result.get("title"))
        url = _clean(raw_result.get("url"))
        description = _clean(raw_result.get("description")) or _clean(raw_result.get("content"))
        if not title or not url:
            continue
        source_domain = urlparse(url).netloc.strip().lower()
        if source_domain not in _ALLOWED_LISTING_DOMAINS:
            continue
        classification = classify_listing_candidate(
            title=title,
            description=description,
            search_category=query.search_category,
        )
        address_hint = _clean(raw_result.get("address_hint")) or candidate_address_hint(title)
        candidate_municipality = extract_municipality_hint(address_hint, title, description)
        candidate_zip_code = extract_zip_code(address_hint, title, description)
        municipality_match = municipality_matches_subject(
            subject_municipality=subject_municipality,
            candidate_municipality=candidate_municipality,
        )
        zip_match = zip_matches_subject(
            subject_zip_code=subject_zip_code,
            candidate_zip_code=candidate_zip_code,
        )
        normalized.append(
            {
                "title": title,
                "url": url,
                "address_hint": address_hint,
                "source_domain": source_domain,
                "query": query.query,
                "description": description,
                "candidate_kind": "listing_candidate",
                "classification": classification,
                "confidence": candidate_confidence(
                    title=title,
                    description=description,
                    search_category=query.search_category,
                    municipality_match=municipality_match,
                    zip_match=zip_match,
                ),
                "search_category": query.search_category,
                "search_window_months": query.window_months,
                "municipality": candidate_municipality,
                "municipality_match": municipality_match,
                "zip_code": candidate_zip_code,
                "zip_match": zip_match,
                "locality_score": locality_score(
                    municipality_match=municipality_match,
                    zip_match=zip_match,
                ),
            }
        )
    return rank_listing_candidates(normalized)


def candidate_address_hint(title: str) -> str:
    return title.split("|", maxsplit=1)[0].strip()


def classify_listing_candidate(*, title: str, description: str, search_category: str = "") -> str:
    haystack = f"{title} {description}".casefold()
    has_improved_signal = any(keyword in haystack for keyword in _IMPROVED_LISTING_KEYWORDS)
    has_land_signal = any(keyword in haystack for keyword in _LAND_LISTING_KEYWORDS)
    has_sold_land_facts = (
        search_category == "sold_land"
        and extract_sold_price(haystack) is not None
        and extract_lot_size_sqft(haystack) is not None
    )
    if has_sold_land_facts or has_land_signal:
        return "likely_vacant_land"
    if has_improved_signal:
        return "likely_improved_sale"
    return "unknown"


def candidate_confidence(
    *,
    title: str,
    description: str,
    search_category: str,
    municipality_match: bool,
    zip_match: bool | None,
) -> float:
    classification = classify_listing_candidate(
        title=title,
        description=description,
        search_category=search_category,
    )
    base_score = _base_candidate_score(
        classification=classification,
        search_category=search_category,
    )
    if municipality_match:
        base_score += 0.03
    else:
        base_score -= 0.1
    match zip_match:
        case True:
            base_score += 0.05
        case False:
            base_score -= 0.03
        case None:
            pass
    return round(min(0.99, max(0.0, base_score)), 3)


def listing_query_should_stop(
    candidates: list[JsonObject],
    *,
    query: ListingQuery,
) -> bool:
    if query.search_category == "sold_land":
        return _land_candidate_support_count(candidates) >= 2
    return any(
        str(candidate.get("classification") or "") == "likely_improved_sale"
        and _is_local_candidate(candidate)
        for candidate in candidates
    )


def rank_listing_candidates(candidates: list[JsonObject]) -> list[JsonObject]:
    ranked_by_key: dict[str, JsonObject] = {}
    for candidate in candidates:
        key = candidate_dedupe_key(candidate)
        existing = ranked_by_key.get(key)
        if existing is None or candidate_sort_key(candidate) < candidate_sort_key(existing):
            ranked_by_key[key] = candidate
    return sorted(ranked_by_key.values(), key=candidate_sort_key)


def candidate_dedupe_key(candidate: JsonObject) -> str:
    url = _clean(candidate.get("url")).casefold()
    if url:
        return url
    return _clean(candidate.get("address_hint")).casefold()


def candidate_sort_key(candidate: JsonObject) -> tuple[object, ...]:
    confidence = candidate.get("confidence")
    numeric_confidence = float(confidence) if isinstance(confidence, int | float) else 0.0
    locality = candidate.get("locality_score")
    locality_score_value = float(locality) if isinstance(locality, int | float) else 0.0
    return (
        str(candidate.get("classification") or "") != "likely_vacant_land",
        candidate.get("zip_match") is not True,
        candidate.get("municipality_match") is not True,
        -locality_score_value,
        -numeric_confidence,
        int(candidate.get("search_window_months") or 999),
        _clean(candidate.get("address_hint")).casefold(),
        _clean(candidate.get("url")).casefold(),
    )


def locality_score(*, municipality_match: bool, zip_match: bool | None) -> float:
    score = 0.0
    if municipality_match:
        score += 0.6
    match zip_match:
        case True:
            score += 0.4
        case False:
            score -= 0.2
        case None:
            pass
    return round(score, 3)


def _base_candidate_score(*, classification: str, search_category: str) -> float:
    if classification == "likely_vacant_land" and search_category == "sold_land":
        return 0.9
    if classification == "likely_improved_sale" and search_category in {
        "new_build_houses",
        "renovated_houses",
    }:
        return 0.88
    if classification == "likely_improved_sale":
        return 0.8
    if classification == "likely_vacant_land":
        return 0.75
    return 0.3


def _land_candidate_support_count(candidates: list[JsonObject]) -> int:
    supported_addresses: set[str] = set()
    for candidate in candidates:
        if str(candidate.get("classification") or "") != "likely_vacant_land":
            continue
        confidence = candidate.get("confidence")
        if not isinstance(confidence, int | float) or float(confidence) < 0.75:
            continue
        if not _is_local_candidate(candidate):
            continue
        address_hint = _clean(candidate.get("address_hint")).casefold()
        if not address_hint:
            continue
        supported_addresses.add(address_hint)
    return len(supported_addresses)


def _is_local_candidate(candidate: JsonObject) -> bool:
    if candidate.get("municipality_match") is not True:
        return False
    locality = candidate.get("locality_score")
    if isinstance(locality, int | float):
        return float(locality) >= 0.4
    return candidate.get("zip_match") is True


def _clean(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
