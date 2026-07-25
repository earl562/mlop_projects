from __future__ import annotations

import pytest

from plotlot.harness.listing_comp_verification import (
    build_contextual_land_listing_verification,
)


def test_build_contextual_land_listing_verification_extracts_acreage_when_sqft_missing() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-acreage",
                "title": "Vacant lot listing",
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            }
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-acreage",
                "description": "Sold for $135,000 on 04/21/2026.",
                "content": "Closed at $135,000 on 0.21 acres.",
            }
        ],
        subject_lot_area_sf=10105.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 1
    assert result["verified_candidates"][0]["lot_size_sqft"] == 9147.6
    assert result["verified_candidates"][0]["sale_date"] == "2026-04-21"
    assert result["verified_candidates"][0]["municipality"] == "Miami Gardens"
    assert result["verified_candidates"][0]["municipality_match"] is True
    assert result["verified_candidates"][0]["zip_code"] == "33056"
    assert result["verified_candidates"][0]["zip_match"] is False
    assert result["verified_candidates"][0]["parsing_confidence"] == pytest.approx(1.0)


def test_build_contextual_land_listing_verification_extracts_dimensions_when_sqft_missing() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-dimensions",
                "title": "Buildable lot listing",
                "address_hint": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold lot listing.",
                "search_window_months": 12,
            }
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-dimensions",
                "description": "Sold for $145,000.",
                "content": "Sold price $145,000. Sold on Apr 21, 2026. Lot dimensions 75 x 120.",
            }
        ],
        subject_lot_area_sf=10105.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 1
    assert result["verified_candidates"][0]["lot_size_sqft"] == 9000.0
    assert result["verified_candidates"][0]["sale_date"] == "2026-04-21"


def test_build_contextual_land_listing_verification_rejects_sales_outside_search_window() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-stale",
                "title": "Sold lot listing",
                "address_hint": "168 Terrace, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 6,
            }
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-stale",
                "description": "Sold for $152,000 on 2025-10-15.",
                "content": "Sold for $152,000 on 2025-10-15. Lot size 8,900 sqft.",
            }
        ],
        subject_lot_area_sf=10105.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 0
    assert result["verified_candidates"] == []


def test_build_contextual_land_listing_verification_rejects_lot_sizes_that_are_not_similar() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-mismatch",
                "title": "Oversized lot sale",
                "address_hint": "999 Example Rd, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            }
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-mismatch",
                "description": "Sold for $210,000 on 2026-04-21.",
                "content": "Sold for $210,000 on 2026-04-21. Lot size 18,500 sqft.",
            }
        ],
        subject_lot_area_sf=10105.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 0
    assert result["verified_candidates"] == []


def test_build_contextual_land_listing_verification_orders_candidates_by_best_lot_fit() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-close-fit",
                "title": "Close fit lot",
                "address_hint": "100 Close Fit Rd, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            },
            {
                "url": "https://www.zillow.com/homedetails/example-looser-fit",
                "title": "Looser fit lot",
                "address_hint": "200 Looser Fit Rd, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            },
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-close-fit",
                "description": "Sold for $140,000 on 2026-04-21.",
                "content": "Sold for $140,000 on 2026-04-21. Lot size 10,000 sqft.",
            },
            {
                "url": "https://www.zillow.com/homedetails/example-looser-fit",
                "description": "Sold for $135,000 on 2026-04-21.",
                "content": "Sold for $135,000 on 2026-04-21. Lot size 8,400 sqft.",
            },
        ],
        subject_lot_area_sf=10105.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 2
    assert result["verified_candidates"][0]["address_hint"] == "100 Close Fit Rd, Miami Gardens, FL 33056"
    assert result["verified_candidates"][0]["fit_score"] > result["verified_candidates"][1]["fit_score"]
    assert result["verified_candidates"][0]["lot_size_variance_ratio"] < (
        result["verified_candidates"][1]["lot_size_variance_ratio"]
    )
    assert all(candidate["municipality_match"] is True for candidate in result["verified_candidates"])


def test_build_contextual_land_listing_verification_rejects_explicit_municipality_mismatch() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-other-city",
                "title": "Other city lot",
                "address_hint": "100 Sample Ave, Opa-locka, FL 33054",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            }
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-other-city",
                "description": "Sold for $142,000 on 2026-04-21.",
                "content": "Sold for $142,000 on 2026-04-21. Lot size 9,800 sqft.",
            }
        ],
        subject_lot_area_sf=10105.0,
        subject_municipality="Miami Gardens",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 0
    assert result["verified_candidates"] == []


def test_build_contextual_land_listing_verification_prefers_same_zip_candidate() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "url": "https://www.zillow.com/homedetails/example-same-zip",
                "title": "Same zip lot",
                "address_hint": "100 Near Lot Rd, Miami Gardens, FL 33169",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            },
            {
                "url": "https://www.zillow.com/homedetails/example-other-zip",
                "title": "Other zip lot",
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "classification": "likely_vacant_land",
                "description": "Sold vacant lot.",
                "search_window_months": 12,
            },
        ],
        fetched_results=[
            {
                "url": "https://www.zillow.com/homedetails/example-same-zip",
                "description": "Sold for $141,000 on 2026-04-21.",
                "content": "Sold for $141,000 on 2026-04-21. Lot size 10,000 sqft.",
            },
            {
                "url": "https://www.zillow.com/homedetails/example-other-zip",
                "description": "Sold for $140,000 on 2026-04-21.",
                "content": "Sold for $140,000 on 2026-04-21. Lot size 10,000 sqft.",
            },
        ],
        subject_lot_area_sf=10105.0,
        subject_municipality="Miami Gardens",
        subject_address="45 NW 209 ST, Miami Gardens, FL 33169",
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 2
    assert result["verified_candidates"][0]["address_hint"] == "100 Near Lot Rd, Miami Gardens, FL 33169"
    assert result["verified_candidates"][0]["zip_match"] is True
    assert result["verified_candidates"][1]["zip_match"] is False
