"""Tests for Zillow comps skill integration in deal analysis."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import (
    DensityAnalysis,
    NumericZoningParams,
    PropertyRecord,
    ZoningReport,
)
from plotlot.pipeline.deal_analysis import run_deal_analysis
from plotlot.pipeline.skills.registry import HandlerResult


def _report_with_density_and_record(
    property_type: str,
    max_units: int = 6,
) -> ZoningReport:
    return ZoningReport(
        address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        municipality="Miramar",
        county="Broward",
        property_record=PropertyRecord(
            address="7940 Plantation Blvd",
            lot_size_sqft=7500,
            building_area_sqft=1400,
        ),
        numeric_params=NumericZoningParams(property_type=property_type),
        density_analysis=DensityAnalysis(
            max_units=max_units,
            governing_constraint="test",
            constraints=[],
        ),
    )


def _zillow_comp(listing_type: str, price: float = 2800.0) -> dict:
    return {
        "source": "zillow",
        "source_id": "12345",
        "address": "123 Main St",
        "price": price,
        "bedrooms": 2,
        "bathrooms": 2,
        "sqft": 1400,
        "lot_sqft": 7200,
        "year_built": 2010,
        "property_type": "SINGLE_FAMILY",
        "sold_date": "2024-01-15" if listing_type in ("sold", "land", "new_build", "renovated", "small_mf") else None,
        "latitude": 26.0,
        "longitude": -80.0,
        "source_url": "https://www.zillow.com/sample",
    }


@pytest.mark.asyncio
async def test_zillow_comps_land_uses_land_listing_type():
    report = _report_with_density_and_record("land")

    with patch(
        "plotlot.pipeline.skills.playwright_comps.handle_fetch_zillow_comps",
        new_callable=AsyncMock,
        return_value=HandlerResult(
            output_json={"comparables": [_zillow_comp("land")], "source": "zillow", "count": 1},
            evidence_ids=[],
        ),
    ) as mock_zillow:
        analysis = await run_deal_analysis(
            zoning_report=report,
            county="broward",
            state="FL",
            land_purchase_price=500_000,
            zip_code="33023",
        )

    mock_zillow.assert_awaited_once()
    call_args = mock_zillow.call_args[0][0]
    assert call_args["listing_type"] == "land"
    assert analysis.rental_comp_set is not None


@pytest.mark.asyncio
async def test_zillow_comps_residential_uses_rental_listings():
    report = _report_with_density_and_record("multifamily")

    with patch(
        "plotlot.pipeline.skills.playwright_comps.handle_fetch_zillow_comps",
        new_callable=AsyncMock,
        return_value=HandlerResult(
            output_json={"comparables": [_zillow_comp("rental")], "source": "zillow", "count": 1},
            evidence_ids=[],
        ),
    ) as mock_zillow:
        await run_deal_analysis(
            zoning_report=report,
            county="broward",
            state="FL",
            land_purchase_price=500_000,
            zip_code="33023",
        )

    mock_zillow.assert_awaited_once()
    call_args = mock_zillow.call_args[0][0]
    assert call_args["listing_type"] == "rental"


@pytest.mark.asyncio
async def test_zillow_comps_small_residential_uses_new_build_listings():
    report = _report_with_density_and_record("single_family", max_units=4)

    with patch(
        "plotlot.pipeline.skills.playwright_comps.handle_fetch_zillow_comps",
        new_callable=AsyncMock,
        return_value=HandlerResult(
            output_json={"comparables": [_zillow_comp("new_build")], "source": "zillow", "count": 1},
            evidence_ids=[],
        ),
    ) as mock_zillow:
        await run_deal_analysis(
            zoning_report=report,
            county="broward",
            state="FL",
            land_purchase_price=500_000,
            zip_code="33023",
        )

    mock_zillow.assert_awaited_once()
    call_args = mock_zillow.call_args[0][0]
    assert call_args["listing_type"] == "new_build"


@pytest.mark.asyncio
async def test_zillow_comps_small_mf_uses_small_mf_listings():
    report = _report_with_density_and_record("multifamily", max_units=3)

    with patch(
        "plotlot.pipeline.skills.playwright_comps.handle_fetch_zillow_comps",
        new_callable=AsyncMock,
        return_value=HandlerResult(
            output_json={"comparables": [_zillow_comp("small_mf")], "source": "zillow", "count": 1},
            evidence_ids=[],
        ),
    ) as mock_zillow:
        await run_deal_analysis(
            zoning_report=report,
            county="broward",
            state="FL",
            land_purchase_price=500_000,
            zip_code="33023",
        )

    mock_zillow.assert_awaited_once()
    call_args = mock_zillow.call_args[0][0]
    assert call_args["listing_type"] == "small_mf"


@pytest.mark.asyncio
async def test_zillow_comps_empty_results_handled():
    report = _report_with_density_and_record("land")

    with patch(
        "plotlot.pipeline.skills.playwright_comps.handle_fetch_zillow_comps",
        new_callable=AsyncMock,
        return_value=HandlerResult(
            output_json={"comparables": [], "source": "zillow", "count": 0},
            evidence_ids=[],
        ),
    ):
        analysis = await run_deal_analysis(
            zoning_report=report,
            county="broward",
            state="FL",
            land_purchase_price=500_000,
            zip_code="33023",
        )

    assert analysis.rental_comp_set is not None
    assert any("no listings" in n.lower() or "no rental" in n.lower() for n in analysis.notes)
