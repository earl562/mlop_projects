from __future__ import annotations

from plotlot.harness.fixture_runs import (
    _county_reconciled_pricing_candidates,
    CountyReconciliationCandidate,
    _county_reconciliation_candidates,
    _listing_candidate_matches_county_record,
)


def test_county_reconciliation_candidates_prefers_highest_confidence_three() -> None:
    ranked = _county_reconciliation_candidates(
        [
            {"address_hint": "A", "confidence": 0.31},
            {"address_hint": "B", "confidence": 0.72},
            {"address_hint": "C", "confidence": 0.65},
            {"address_hint": "D", "confidence": 0.88},
        ]
    )

    assert [str(candidate["address_hint"]) for candidate in ranked] == ["D", "B", "C"]


def test_county_reconciliation_candidates_prefers_best_lot_fit_before_confidence() -> None:
    ranked = _county_reconciliation_candidates(
        [
            {"address_hint": "A", "fit_score": 0.81, "lot_size_variance_ratio": 0.19, "confidence": 0.9},
            {"address_hint": "B", "fit_score": 0.94, "lot_size_variance_ratio": 0.06, "confidence": 0.72},
            {"address_hint": "C", "fit_score": 0.89, "lot_size_variance_ratio": 0.11, "confidence": 0.95},
        ]
    )

    assert [str(candidate["address_hint"]) for candidate in ranked] == ["B", "C", "A"]


def test_county_reconciliation_candidates_prefers_subject_zip_before_cross_zip() -> None:
    ranked = _county_reconciliation_candidates(
        [
            {
                "address_hint": "Cross Zip",
                "fit_score": 0.97,
                "lot_size_variance_ratio": 0.03,
                "parsing_confidence": 1.0,
                "confidence": 0.9,
                "municipality_match": True,
                "zip_match": False,
            },
            {
                "address_hint": "Subject Zip",
                "fit_score": 0.94,
                "lot_size_variance_ratio": 0.06,
                "parsing_confidence": 0.9,
                "confidence": 0.82,
                "municipality_match": True,
                "zip_match": True,
            },
        ]
    )

    assert [str(candidate["address_hint"]) for candidate in ranked] == ["Subject Zip", "Cross Zip"]


def test_county_reconciliation_candidates_dedupes_same_address_to_best_candidate() -> None:
    ranked = _county_reconciliation_candidates(
        [
            {
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "fit_score": 0.89,
                "lot_size_variance_ratio": 0.11,
                "parsing_confidence": 0.8,
                "confidence": 0.75,
                "municipality_match": True,
                "zip_match": False,
            },
            {
                "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "fit_score": 0.93,
                "lot_size_variance_ratio": 0.07,
                "parsing_confidence": 1.0,
                "confidence": 0.9,
                "municipality_match": True,
                "zip_match": True,
            },
            {
                "address_hint": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                "fit_score": 0.9,
                "lot_size_variance_ratio": 0.1,
                "parsing_confidence": 0.95,
                "confidence": 0.88,
                "municipality_match": True,
                "zip_match": False,
            },
        ]
    )

    assert len(ranked) == 2
    assert str(ranked[0]["address_hint"]) == "17605 NW 19th Avenue, Miami Gardens, FL 33056"
    assert ranked[0]["zip_match"] is True


def test_county_reconciled_pricing_candidates_prefers_subject_zip_subset() -> None:
    pricing_candidates = _county_reconciled_pricing_candidates(
        [
            {
                "address_hint": "Cross Zip 1",
                "zip_match": False,
                "municipality_match": True,
                "county_price_per_acre": 620000.0,
            },
            {
                "address_hint": "Subject Zip 1",
                "zip_match": True,
                "municipality_match": True,
                "county_price_per_acre": 700000.0,
            },
            {
                "address_hint": "Subject Zip 2",
                "zip_match": True,
                "municipality_match": True,
                "county_price_per_acre": 710000.0,
            },
        ]
    )

    assert [str(candidate["address_hint"]) for candidate in pricing_candidates] == [
        "Subject Zip 1",
        "Subject Zip 2",
    ]


def test_county_reconciled_pricing_candidates_falls_back_to_subject_municipality_subset() -> None:
    pricing_candidates = _county_reconciled_pricing_candidates(
        [
            {
                "address_hint": "Cross Municipality",
                "zip_match": False,
                "municipality_match": False,
                "county_price_per_acre": 580000.0,
            },
            {
                "address_hint": "Same Municipality 1",
                "zip_match": False,
                "municipality_match": True,
                "county_price_per_acre": 640000.0,
            },
            {
                "address_hint": "Same Municipality 2",
                "zip_match": False,
                "municipality_match": True,
                "county_price_per_acre": 650000.0,
            },
        ]
    )

    assert [str(candidate["address_hint"]) for candidate in pricing_candidates] == [
        "Same Municipality 1",
        "Same Municipality 2",
    ]


def test_listing_candidate_matches_county_record_rejects_address_mismatch() -> None:
    matches = _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=150000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="2940 NW 169th Ter, Miami Gardens, FL 33056",
            county_sale_price=151000.0,
            county_sale_date="2026-04-30",
            county_lot_size_sqft=9050.0,
        )
    )

    assert matches is False


def test_listing_candidate_matches_county_record_accepts_aligned_address_and_metrics() -> None:
    matches = _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=150000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 NW 19th Ave, Miami Gardens, FL 33056",
            county_sale_price=151000.0,
            county_sale_date="2026-04-30",
            county_lot_size_sqft=9050.0,
        )
    )

    assert matches is True
