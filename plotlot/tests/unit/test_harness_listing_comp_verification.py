from __future__ import annotations

from plotlot.harness.listing_comp_verification import build_contextual_land_listing_verification


def test_build_contextual_land_listing_verification_ignores_non_land_candidates() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "title": "Improved sale",
                "url": "https://example.test/improved",
                "address_hint": "100 Example Ave",
                "classification": "likely_improved_sale",
            }
        ],
        fetched_results=[
            {
                "url": "https://example.test/improved",
                "description": "Sold for $400,000 on 2026-04-21. Lot size 8,000 sqft.",
                "content": "Sold for $400,000 on 2026-04-21. Lot size 8,000 sqft.",
            }
        ],
        subject_lot_area_sf=10_105.0,
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 0
    assert result["verified_candidates"] == []
    assert result["review_candidate_count"] == 0
    assert result["review_candidates"] == []
    assert result["estimated_land_value"] == 0.0


def test_build_contextual_land_listing_verification_requires_sale_price_and_lot_size() -> None:
    result = build_contextual_land_listing_verification(
        candidates=[
            {
                "title": "Missing sold price",
                "url": "https://example.test/no-sale-price",
                "address_hint": "17605 NW 19th Avenue",
                "classification": "likely_vacant_land",
                "search_window_months": 12,
            },
            {
                "title": "Missing lot size",
                "url": "https://example.test/no-lot-size",
                "address_hint": "2940 NW 169th Ter",
                "classification": "likely_vacant_land",
                "search_window_months": 12,
            },
        ],
        fetched_results=[
            {
                "url": "https://example.test/no-sale-price",
                "description": "Vacant lot in Miami Gardens.",
                "content": "Available lot with 9,000 sqft. Sold on 2026-04-21.",
            },
            {
                "url": "https://example.test/no-lot-size",
                "description": "Sold for $145,000 on 2026-04-21.",
                "content": "Closed at $145,000 on 2026-04-21 with no lot size disclosed.",
            },
        ],
        subject_lot_area_sf=10_105.0,
        reference_date_iso="2026-06-29",
    )

    assert result["verified_candidate_count"] == 0
    assert result["verified_candidates"] == []
    assert result["review_candidate_count"] == 2
    assert {
        candidate["verification_basis"] for candidate in result["review_candidates"]
    } == {"address_only_public_listing"}
    assert all(
        candidate["county_reconciliation_required"] is True
        for candidate in result["review_candidates"]
    )
    assert result["price_per_acre_median"] == 0.0
