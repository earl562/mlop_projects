from __future__ import annotations

from plotlot.harness.comparable_listing_search import (
    build_comparable_listing_queries,
    comparable_listing_query_plan,
    listing_query_should_stop,
    normalize_listing_candidates,
    rank_listing_candidates,
)


def test_build_comparable_listing_queries_uses_land_then_house_fallback() -> None:
    queries = build_comparable_listing_queries(
        {
            "address": "45 NW 209 ST",
            "municipality": "Miami Gardens",
            "county": "Miami-Dade",
            "zoning_code": "R-1",
        }
    )

    assert [query.search_category for query in queries] == [
        "sold_land",
        "sold_land",
        "sold_land",
        "new_build_houses",
        "renovated_houses",
    ]
    assert [query.window_months for query in queries] == [6, 12, 24, 12, 12]
    assert [query.purpose for query in queries] == [
        "primary_recent_land_comp_search",
        "expanded_recent_land_comp_search",
        "maximum_land_comp_lookback_search",
        "exit_value_new_build_fallback_search",
        "exit_value_renovated_sale_fallback_search",
    ]
    assert "Miami Gardens Miami-Dade" in queries[0].query
    assert "R-1" not in queries[0].query
    assert "33169" not in queries[0].query
    assert "45 NW 209 ST" not in queries[0].query
    assert "site:zillow.com OR site:redfin.com" in queries[0].query


def test_comparable_listing_query_plan_exposes_order_and_stop_rules() -> None:
    plan = comparable_listing_query_plan(
        {
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "Miami Gardens",
            "county": "Miami-Dade",
            "zoning_code": "R-1",
        }
    )

    assert [entry["step"] for entry in plan] == [1, 2, 3, 4, 5]
    assert plan[0]["purpose"] == "primary_recent_land_comp_search"
    assert plan[0]["search_window_months"] == 6
    assert plan[2]["purpose"] == "maximum_land_comp_lookback_search"
    assert plan[3]["purpose"] == "exit_value_new_build_fallback_search"
    assert plan[4]["purpose"] == "exit_value_renovated_sale_fallback_search"
    assert plan[0]["stop_rule"] == "continue_until_two_local_land_candidates_or_expand_window"
    assert all("R-1" not in entry["query"] for entry in plan)


def test_build_comparable_listing_queries_includes_subject_zip_when_known() -> None:
    queries = build_comparable_listing_queries(
        {
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "Miami Gardens",
            "county": "Miami-Dade",
            "zoning_code": "R-1",
        }
    )

    assert "33169" in queries[0].query


def test_build_comparable_listing_queries_falls_back_to_address_when_market_area_missing() -> None:
    queries = build_comparable_listing_queries(
        {
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "",
            "county": "",
        }
    )

    assert "45 NW 209 ST, Miami Gardens, FL 33169" in queries[0].query


def test_normalize_listing_candidates_filters_to_zillow_and_redfin() -> None:
    query = build_comparable_listing_queries(
        {"address": "45 NW 209 ST", "municipality": "Miami Gardens", "county": "Miami-Dade"}
    )[0]

    candidates = normalize_listing_candidates(
        [
            {
                "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                "url": "https://www.zillow.com/homedetails/example-land",
                "description": "Sold vacant lot with buildable land.",
            },
            {
                "title": "Off-domain result",
                "url": "https://example.com/listing",
                "description": "Sold vacant lot.",
            },
        ],
        query=query,
        subject_payload={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "Miami Gardens",
        },
    )

    assert len(candidates) == 1
    assert candidates[0]["source_domain"] == "www.zillow.com"
    assert candidates[0]["classification"] == "likely_vacant_land"
    assert candidates[0]["search_window_months"] == 6
    assert candidates[0]["municipality_match"] is True
    assert candidates[0]["zip_match"] is False


def test_sold_land_query_treats_zillow_property_record_with_sale_and_lot_facts_as_land() -> None:
    query = build_comparable_listing_queries(
        {
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "Miami Gardens",
            "county": "Miami-Dade",
        }
    )[0]

    candidates = normalize_listing_candidates(
        [
            {
                "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                "url": "https://www.zillow.com/homedetails/17605-NW-19th-Ave/44106704_zpid/",
                "description": "Zillow home details. Sold for $135,000 on 2025-12-01. 9,000 sqft lot.",
            }
        ],
        query=query,
        subject_payload={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "municipality": "Miami Gardens",
        },
    )

    assert candidates[0]["classification"] == "likely_vacant_land"
    assert candidates[0]["confidence"] >= 0.75
    assert candidates[0]["search_category"] == "sold_land"


def test_rank_listing_candidates_prefers_subject_zip_and_dedupes() -> None:
    ranked = rank_listing_candidates(
        [
            {
                "title": "Cross zip first",
                "url": "https://www.zillow.com/homedetails/example-land",
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "confidence": 0.83,
                "municipality_match": True,
                "zip_match": False,
                "locality_score": 0.4,
                "search_window_months": 12,
            },
            {
                "title": "Subject zip duplicate",
                "url": "https://www.zillow.com/homedetails/example-land",
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33169",
                "classification": "likely_vacant_land",
                "confidence": 0.95,
                "municipality_match": True,
                "zip_match": True,
                "locality_score": 1.0,
                "search_window_months": 6,
            },
            {
                "title": "Improved sale",
                "url": "https://www.redfin.com/example-house",
                "address_hint": "100 NW 208th St, Miami Gardens, FL 33169",
                "classification": "likely_improved_sale",
                "confidence": 0.88,
                "municipality_match": True,
                "zip_match": True,
                "locality_score": 1.0,
                "search_window_months": 12,
            },
        ]
    )

    assert len(ranked) == 2
    assert ranked[0]["title"] == "Subject zip duplicate"
    assert ranked[0]["zip_match"] is True
    assert ranked[1]["classification"] == "likely_improved_sale"


def test_listing_query_should_stop_on_improved_sale_house_fallback() -> None:
    query = build_comparable_listing_queries(
        {"address": "45 NW 209 ST", "municipality": "Miami Gardens", "county": "Miami-Dade"}
    )[3]

    should_stop = listing_query_should_stop(
        [
            {
                "classification": "likely_improved_sale",
                "municipality_match": True,
                "locality_score": 1.0,
            }
        ],
        query=query,
    )

    assert should_stop is True


def test_listing_query_should_continue_when_only_one_land_candidate_is_found() -> None:
    query = build_comparable_listing_queries(
        {"address": "45 NW 209 ST", "municipality": "Miami Gardens", "county": "Miami-Dade"}
    )[0]

    should_stop = listing_query_should_stop(
        [
            {
                "classification": "likely_vacant_land",
                "confidence": 0.9,
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "municipality_match": True,
                "locality_score": 0.4,
            }
        ],
        query=query,
    )

    assert should_stop is False


def test_listing_query_should_stop_when_two_unique_land_candidates_are_found() -> None:
    query = build_comparable_listing_queries(
        {"address": "45 NW 209 ST", "municipality": "Miami Gardens", "county": "Miami-Dade"}
    )[0]

    should_stop = listing_query_should_stop(
        [
            {
                "classification": "likely_vacant_land",
                "confidence": 0.9,
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "municipality_match": True,
                "locality_score": 0.4,
            },
            {
                "classification": "likely_vacant_land",
                "confidence": 0.9,
                "address_hint": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                "municipality_match": True,
                "locality_score": 0.4,
            },
        ],
        query=query,
    )

    assert should_stop is True


def test_listing_query_should_not_stop_on_non_local_land_candidates() -> None:
    query = build_comparable_listing_queries(
        {"address": "45 NW 209 ST", "municipality": "Miami Gardens", "county": "Miami-Dade"}
    )[0]

    should_stop = listing_query_should_stop(
        [
            {
                "classification": "likely_vacant_land",
                "confidence": 0.9,
                "address_hint": "Somewhere Else, Opa-locka, FL 33054",
                "municipality_match": False,
                "locality_score": -0.2,
            },
            {
                "classification": "likely_vacant_land",
                "confidence": 0.9,
                "address_hint": "Another Place, Miami, FL 33150",
                "municipality_match": False,
                "locality_score": -0.2,
            },
        ],
        query=query,
    )

    assert should_stop is False
