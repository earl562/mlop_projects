from __future__ import annotations

from plotlot.harness.exit_comp_support import best_exit_comp_snapshot


def test_best_exit_comp_snapshot_prefers_highest_quality_recent_same_market_comp() -> None:
    snapshot = best_exit_comp_snapshot(
        unit_comparables=[
            {
                "address": "105 NE 213 ST, Miami Gardens, FL 33179",
                "sale_date": "2026-04-21",
                "distance_miles": 0.34,
                "price_per_unit": 699000.0,
                "adjustments": {"qualification_score": 0.92},
            },
            {
                "address": "450 Premium Build Ct, Miami Gardens, FL 33056",
                "sale_date": "2026-01-12",
                "distance_miles": 1.42,
                "price_per_unit": 715000.0,
                "adjustments": {"qualification_score": 0.84},
            },
        ],
        adv_per_unit=699000.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33179",
    )

    assert snapshot == {
        "exit_support_distance_miles": 0.34,
        "exit_support_market_scope": "subject_zip",
        "exit_support_zip_match": True,
        "exit_support_sale_date": "2026-04-21",
        "exit_support_recency_tier": "recent_6m",
    }


def test_best_exit_comp_snapshot_marks_municipality_mismatch() -> None:
    snapshot = best_exit_comp_snapshot(
        unit_comparables=[
            {
                "address": "Remote Comp, Opa-locka, FL 33054",
                "sale_date": "2025-12-01",
                "distance_miles": 4.7,
                "price_per_unit": 510000.0,
                "adjustments": {
                    "qualification_score": 0.58,
                    "municipality_mismatch": 1.0,
                },
            }
        ],
        adv_per_unit=500000.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33179",
    )

    assert snapshot == {
        "exit_support_distance_miles": 4.7,
        "exit_support_market_scope": "outside_subject_municipality",
        "exit_support_zip_match": False,
        "exit_support_sale_date": "2025-12-01",
        "exit_support_recency_tier": "recent_12m",
    }


def test_best_exit_comp_snapshot_marks_cross_zip_same_municipality() -> None:
    snapshot = best_exit_comp_snapshot(
        unit_comparables=[
            {
                "address": "115 NE 213 ST, Miami Gardens, FL 33169",
                "sale_date": "2026-04-21",
                "distance_miles": 0.42,
                "price_per_unit": 699000.0,
                "adjustments": {"qualification_score": 0.9},
            }
        ],
        adv_per_unit=699000.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33179",
    )

    assert snapshot == {
        "exit_support_distance_miles": 0.42,
        "exit_support_market_scope": "cross_zip_same_municipality",
        "exit_support_zip_match": False,
        "exit_support_sale_date": "2026-04-21",
        "exit_support_recency_tier": "recent_6m",
    }


def test_best_exit_comp_snapshot_prefers_more_local_market_scope_over_higher_qualification() -> None:
    snapshot = best_exit_comp_snapshot(
        unit_comparables=[
            {
                "address": "Cross Zip Stronger Score, Miami Gardens, FL 33169",
                "sale_date": "2026-04-21",
                "distance_miles": 0.2,
                "price_per_unit": 699000.0,
                "adjustments": {"qualification_score": 0.98},
            },
            {
                "address": "Subject Zip Slightly Lower Score, Miami Gardens, FL 33179",
                "sale_date": "2026-03-18",
                "distance_miles": 0.5,
                "price_per_unit": 699000.0,
                "adjustments": {"qualification_score": 0.88},
            },
        ],
        adv_per_unit=699000.0,
        subject_address="45 NW 209 ST, Miami Gardens, FL 33179",
    )

    assert snapshot == {
        "exit_support_distance_miles": 0.5,
        "exit_support_market_scope": "subject_zip",
        "exit_support_zip_match": True,
        "exit_support_sale_date": "2026-03-18",
        "exit_support_recency_tier": "recent_6m",
    }
