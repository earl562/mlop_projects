from __future__ import annotations

import pytest

from plotlot.harness.fixture_runs import (
    _build_live_acquisition_guidance,
    _has_direct_land_comp_signal,
    _has_supported_relaxed_land_comp_signal,
    _land_comp_quality_summary,
    _merge_live_land_comp_payloads,
    _unit_comp_quality_summary,
)


def _land_comp(
    *,
    address: str,
    sale_price: float,
    sale_date: str,
    lot_size_sqft: float,
    distance_miles: float,
    qualification_score: float,
) -> dict[str, object]:
    return {
        "address": address,
        "sale_price": sale_price,
        "sale_date": sale_date,
        "lot_size_sqft": lot_size_sqft,
        "distance_miles": distance_miles,
        "adjustments": {"qualification_score": qualification_score},
    }


def test_land_comp_quality_summary_treats_near_duplicate_lot_cluster_as_one_signal() -> None:
    comps_payload: dict[str, object] = {
        "comparables": [
            _land_comp(
                address="3421100011870",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.73,
                qualification_score=0.932,
            ),
            _land_comp(
                address="3421100011880",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.73,
                qualification_score=0.932,
            ),
            _land_comp(
                address="3421100011890",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.74,
                qualification_score=0.932,
            ),
            _land_comp(
                address="3421100011900",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.74,
                qualification_score=0.932,
            ),
        ],
        "estimated_land_value": 329625.52,
        "confidence": 0.75,
        "notes": [],
    }

    summary = _land_comp_quality_summary(comps_payload)

    assert summary["land_comp_count"] == 4
    assert summary["strong_land_comp_count"] == 4
    assert summary["independent_land_comp_count"] == 1
    assert summary["strong_independent_land_comp_count"] == 1
    assert summary["direct_land_comp_signal"] is False
    assert _has_direct_land_comp_signal(comps_payload) is False


def test_land_comp_quality_summary_accepts_two_independent_strong_land_comps() -> None:
    comps_payload: dict[str, object] = {
        "comparables": [
            _land_comp(
                address="3421100011870",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.73,
                qualification_score=0.932,
            ),
            _land_comp(
                address="17605 NW 19th Avenue",
                sale_price=185000.0,
                sale_date="20251217",
                lot_size_sqft=7875.0,
                distance_miles=3.99,
                qualification_score=0.871,
            ),
        ],
        "subject_lot_size_sqft": 8000.0,
        "estimated_land_value": 257500.0,
        "confidence": 0.75,
        "notes": [],
    }

    summary = _land_comp_quality_summary(comps_payload)

    assert summary["independent_land_comp_count"] == 2
    assert summary["strong_independent_land_comp_count"] == 2
    assert summary["best_fit_score"] == pytest.approx(0.984)
    assert summary["best_fit_lot_size_variance_ratio"] == pytest.approx(0.016)
    assert summary["best_fit_qualification_score"] == pytest.approx(0.871)
    assert summary["direct_land_comp_signal"] is True
    assert _has_direct_land_comp_signal(comps_payload) is True


def test_direct_land_comp_signal_rejects_strong_but_poor_fit_land_comps() -> None:
    comps_payload: dict[str, object] = {
        "comparables": [
            _land_comp(
                address="17605 NW 19th Avenue",
                sale_price=185000.0,
                sale_date="20251217",
                lot_size_sqft=18000.0,
                distance_miles=3.99,
                qualification_score=0.871,
            ),
            _land_comp(
                address="2940 NW 169th Ter",
                sale_price=179000.0,
                sale_date="20251110",
                lot_size_sqft=19250.0,
                distance_miles=4.12,
                qualification_score=0.812,
            ),
        ],
        "subject_lot_size_sqft": 8000.0,
        "estimated_land_value": 182000.0,
        "confidence": 0.75,
        "notes": [],
    }

    summary = _land_comp_quality_summary(comps_payload)

    assert summary["independent_land_comp_count"] == 2
    assert summary["strong_independent_land_comp_count"] == 2
    assert summary["best_fit_score"] < 0.8
    assert summary["best_fit_lot_size_variance_ratio"] > 0.2
    assert summary["direct_land_comp_signal"] is False
    assert _has_direct_land_comp_signal(comps_payload) is False


def test_merge_live_land_comp_payloads_supports_relaxed_signal_across_search_radii() -> None:
    near_cluster_payload: dict[str, object] = {
        "comparables": [
            _land_comp(
                address="3421100011870",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.73,
                qualification_score=0.65,
            ),
            _land_comp(
                address="3421100011880",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.73,
                qualification_score=0.65,
            ),
            _land_comp(
                address="3421100011890",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.74,
                qualification_score=0.65,
            ),
            _land_comp(
                address="3421100011900",
                sale_price=250000.0,
                sale_date="20260324",
                lot_size_sqft=7664.0,
                distance_miles=2.74,
                qualification_score=0.65,
            ),
        ],
        "estimated_land_value": 329625.52,
        "estimated_land_value_low": 329625.52,
        "estimated_land_value_high": 329625.52,
        "confidence": 0.45,
        "notes": ["Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."],
        "used_relaxed_land_comps": True,
    }
    wider_payload: dict[str, object] = {
        "comparables": [
            _land_comp(
                address="850 NW 207 ST",
                sale_price=132000.0,
                sale_date="20250421",
                lot_size_sqft=8608.0,
                distance_miles=4.12,
                qualification_score=0.65,
            )
        ],
        "estimated_land_value": 156924.71,
        "estimated_land_value_low": 156924.71,
        "estimated_land_value_high": 156924.71,
        "confidence": 0.45,
        "notes": ["Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."],
        "used_relaxed_land_comps": True,
    }

    merged = _merge_live_land_comp_payloads(
        primary_payload=near_cluster_payload,
        attempt_payloads=[near_cluster_payload, wider_payload],
        subject_lot_size_sqft=10105.0,
    )

    assert len(merged["comparables"]) == 5
    assert _has_direct_land_comp_signal(merged) is False
    assert _has_supported_relaxed_land_comp_signal(merged) is True


def test_merge_live_land_comp_payloads_dedupes_same_county_record_with_variant_address_labels() -> None:
    first_payload: dict[str, object] = {
        "comparables": [
            {
                **_land_comp(
                    address="17605 NW 19th Avenue",
                    sale_price=145000.0,
                    sale_date="20260201",
                    lot_size_sqft=9500.0,
                    distance_miles=4.12,
                    qualification_score=0.82,
                ),
                "provider": "county_recorded_sales",
                "source_url": "https://example.test/arcgis-sale/17605",
            }
        ],
        "estimated_land_value": 145000.0,
        "confidence": 0.55,
        "notes": [],
    }
    second_payload: dict[str, object] = {
        "comparables": [
            {
                **_land_comp(
                    address="17605 NW 19th Ave",
                    sale_price=145000.0,
                    sale_date="20260201",
                    lot_size_sqft=9500.0,
                    distance_miles=4.12,
                    qualification_score=0.82,
                ),
                "provider": "county_recorded_sales",
                "source_url": "https://example.test/arcgis-sale/17605",
            },
            {
                **_land_comp(
                    address="2940 NW 169th Ter",
                    sale_price=152000.0,
                    sale_date="20260115",
                    lot_size_sqft=9800.0,
                    distance_miles=4.38,
                    qualification_score=0.79,
                ),
                "provider": "county_recorded_sales",
                "source_url": "https://example.test/arcgis-sale/2940",
            },
        ],
        "estimated_land_value": 148500.0,
        "confidence": 0.55,
        "notes": [],
    }

    merged = _merge_live_land_comp_payloads(
        primary_payload=first_payload,
        attempt_payloads=[first_payload, second_payload],
        subject_lot_size_sqft=10105.0,
    )

    comparables = merged["comparables"]
    assert len(comparables) == 2
    assert comparables[0]["source_url"] == "https://example.test/arcgis-sale/17605"
    assert comparables[1]["source_url"] == "https://example.test/arcgis-sale/2940"


def test_build_live_acquisition_guidance_flags_supported_relaxed_land_signal_for_validation() -> None:
    comps_payload = _merge_live_land_comp_payloads(
        primary_payload={
            "comparables": [
                _land_comp(
                    address="3421100011870",
                    sale_price=250000.0,
                    sale_date="20260324",
                    lot_size_sqft=7664.0,
                    distance_miles=2.73,
                    qualification_score=0.65,
                ),
                _land_comp(
                    address="3421100011880",
                    sale_price=250000.0,
                    sale_date="20260324",
                    lot_size_sqft=7664.0,
                    distance_miles=2.73,
                    qualification_score=0.65,
                ),
                _land_comp(
                    address="3421100011890",
                    sale_price=250000.0,
                    sale_date="20260324",
                    lot_size_sqft=7664.0,
                    distance_miles=2.74,
                    qualification_score=0.65,
                ),
                _land_comp(
                    address="3421100011900",
                    sale_price=250000.0,
                    sale_date="20260324",
                    lot_size_sqft=7664.0,
                    distance_miles=2.74,
                    qualification_score=0.65,
                ),
            ],
            "estimated_land_value": 329625.52,
            "estimated_land_value_low": 329625.52,
            "estimated_land_value_high": 329625.52,
            "confidence": 0.45,
            "notes": ["Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."],
            "used_relaxed_land_comps": True,
            "adv_per_unit": 452450.0,
        },
        attempt_payloads=[
            {
                "comparables": [
                    _land_comp(
                        address="3421100011870",
                        sale_price=250000.0,
                        sale_date="20260324",
                        lot_size_sqft=7664.0,
                        distance_miles=2.73,
                        qualification_score=0.65,
                    ),
                    _land_comp(
                        address="3421100011880",
                        sale_price=250000.0,
                        sale_date="20260324",
                        lot_size_sqft=7664.0,
                        distance_miles=2.73,
                        qualification_score=0.65,
                    ),
                    _land_comp(
                        address="3421100011890",
                        sale_price=250000.0,
                        sale_date="20260324",
                        lot_size_sqft=7664.0,
                        distance_miles=2.74,
                        qualification_score=0.65,
                    ),
                    _land_comp(
                        address="3421100011900",
                        sale_price=250000.0,
                        sale_date="20260324",
                        lot_size_sqft=7664.0,
                        distance_miles=2.74,
                        qualification_score=0.65,
                    ),
                ],
                "estimated_land_value": 329625.52,
                "estimated_land_value_low": 329625.52,
                "estimated_land_value_high": 329625.52,
                "confidence": 0.45,
                "notes": ["Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."],
                "used_relaxed_land_comps": True,
                "adv_per_unit": 452450.0,
            },
            {
                "comparables": [
                    _land_comp(
                        address="850 NW 207 ST",
                        sale_price=132000.0,
                        sale_date="20250421",
                        lot_size_sqft=8608.0,
                        distance_miles=4.12,
                        qualification_score=0.65,
                    )
                ],
                "estimated_land_value": 156924.71,
                "estimated_land_value_low": 156924.71,
                "estimated_land_value_high": 156924.71,
                "confidence": 0.45,
                "notes": ["Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."],
                "used_relaxed_land_comps": True,
            },
        ],
        subject_lot_size_sqft=10105.0,
    )

    guidance = _build_live_acquisition_guidance(
        property_payload={"last_sale_price": 80000.0},
        comps_payload=comps_payload,
        pro_forma_payload={"max_supportable_land_price": 84837.5},
        residual_payload={},
        underwriting_mode={"mode": "sold_unit_exit", "pricing_source": "auto_comps"},
    )

    assert guidance["recommended_action"] == "insufficient_support"
    assert guidance["basis"] == "supported_relaxed_land_signal_requires_validation"
    assert guidance["land_signal_source"] == "relaxed_land_comps"
    assert guidance["land_signal_strength"] == "supported_relaxed"
    assert guidance["market_signal_verification_status"] == "supported_relaxed"
    assert guidance["requires_market_signal_validation"] is True
    assert guidance["recommendation_confidence"] == "low"


def test_unit_comp_quality_summary_reports_best_exit_fit_metrics() -> None:
    comps_payload: dict[str, object] = {
        "unit_comparables": [
            {
                "address": "105 NE 213 ST",
                "sale_price": 699000.0,
                "sale_date": "2026-04-21",
                "lot_size_sqft": 7500.0,
                "price_per_unit": 446250.0,
                "adjustments": {"qualification_score": 0.9},
            },
            {
                "address": "220 NE 211 ST",
                "sale_price": 594000.0,
                "sale_date": "2026-05-05",
                "lot_size_sqft": 3007.0,
                "price_per_unit": 594000.0,
                "adjustments": {"qualification_score": 0.56},
            },
        ],
        "adv_per_unit": 446250.0,
        "confidence": 0.55,
    }

    summary = _unit_comp_quality_summary(comps_payload)

    assert summary["best_exit_fit_score"] == pytest.approx(1.0)
    assert summary["best_exit_price_variance_ratio"] == pytest.approx(0.0)
    assert summary["best_exit_qualification_score"] == pytest.approx(0.9)
