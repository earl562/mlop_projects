"""Tests for the generalizable comps-source and fee-schedule registries.

These are the "add a market = one entry, not a rewrite" seams. The tests prove:
  * the registries resolve by (state, county) with county normalization,
  * a curated source / itemized schedule overrides the generic fallback,
  * the entitlement and fee wiring use a registered schedule's verified total.
"""

from __future__ import annotations

import pytest

from plotlot.core.types import DensityAnalysis, ZoningReport
from plotlot.pipeline import comps_sources, fee_schedule
from plotlot.pipeline.comps_sources import (
    SalesSource,
    get_sales_source,
    register_sales_source,
    resolve_sales_dataset,
)
from plotlot.pipeline.entitlement import assess_entitlement
from plotlot.pipeline.fee_schedule import (
    FeeComponent,
    FeeSchedule,
    get_fee_schedule,
    register_fee_schedule,
)


@pytest.fixture(autouse=True)
def _restore_registries():
    """Snapshot + restore the module-level registries around each test."""
    sales_before = dict(comps_sources._SALES_SOURCES)
    fees_before = dict(fee_schedule._FEE_SCHEDULES)
    yield
    comps_sources._SALES_SOURCES.clear()
    comps_sources._SALES_SOURCES.update(sales_before)
    fee_schedule._FEE_SCHEDULES.clear()
    fee_schedule._FEE_SCHEDULES.update(fees_before)


# ---------------------------------------------------------------------------
# Fee schedule registry
# ---------------------------------------------------------------------------


def _sd_schedule() -> FeeSchedule:
    return FeeSchedule(
        jurisdiction="City of San Diego",
        state="CA",
        source="City of San Diego FY26 Fee Schedule",
        effective_date="2025-07-01",
        components=(
            FeeComponent("Citywide Mobility DIF", 9000.0, "Resolution R-314273"),
            FeeComponent("Citywide Fire-Rescue DIF", 4000.0, "Resolution R-314271"),
            FeeComponent("Citywide Library DIF", 2000.0, "Resolution R-314272"),
        ),
    )


def test_fee_schedule_total_and_itemized():
    sched = _sd_schedule()
    assert sched.total_per_unit == 15000.0
    assert sched.is_itemized is True
    # An empty schedule is not itemizable.
    empty = FeeSchedule(jurisdiction="X", state="CA")
    assert empty.is_itemized is False


def test_fee_schedule_registry_resolves_with_county_normalization():
    assert get_fee_schedule("CA", "San Diego") is None  # not registered yet
    register_fee_schedule(_sd_schedule(), county="San Diego County")
    assert get_fee_schedule("CA", "San Diego") is not None
    assert get_fee_schedule("ca", "san diego county").total_per_unit == 15000.0


def test_entitlement_uses_registered_schedule_total():
    report = ZoningReport(
        address="x",
        formatted_address="x",
        municipality="San Diego",
        county="San Diego",
        state="CA",
        density_analysis=DensityAnalysis(
            max_units=6, governing_constraint="min_lot_area", constraints=[]
        ),
    )
    # Without a schedule → coarse regional aggregate (San Diego cost model = $40k).
    base = assess_entitlement(report)
    assert base.impact_fee_per_unit == 40000.0

    register_fee_schedule(_sd_schedule(), county="San Diego")
    itemized = assess_entitlement(report)
    assert itemized.impact_fee_per_unit == 15000.0  # the verified schedule total
    assert itemized.impact_fees_total == 90000.0  # 15000 * 6
    assert itemized.fee_market == "City of San Diego"


# ---------------------------------------------------------------------------
# Comps source registry
# ---------------------------------------------------------------------------


def test_sales_source_registry_resolves_with_normalization():
    assert get_sales_source("CA", "San Diego") is None
    register_sales_source(
        "CA",
        "San Diego County",
        SalesSource(
            layer_url="https://example/FeatureServer/0", fields=("SALE_PRICE", "SALE_DATE")
        ),
    )
    assert get_sales_source("ca", "san diego") is not None


@pytest.mark.asyncio
async def test_resolve_sales_dataset_returns_curated_layer():
    register_sales_source(
        "CA",
        "San Diego",
        SalesSource(
            layer_url="https://example/FeatureServer/0",
            fields=("SALE_PRICE", "SALE_DATE", "LOTSIZE"),
            source="test",
        ),
    )
    resolved = await resolve_sales_dataset("CA", "San Diego", 32.75, -117.2, 3.0)
    assert resolved == ("https://example/FeatureServer/0", ["SALE_PRICE", "SALE_DATE", "LOTSIZE"])


@pytest.mark.asyncio
async def test_resolve_sales_dataset_none_when_unregistered():
    assert await resolve_sales_dataset("CA", "Nowhere", 0.0, 0.0, 3.0) is None


@pytest.mark.asyncio
async def test_resolve_sales_dataset_uses_provider_and_isolates_failure():
    async def good_provider(lat, lng, radius):
        return "https://provider/layer/0", ["price", "date"]

    async def bad_provider(lat, lng, radius):
        raise RuntimeError("api down")

    register_sales_source("CA", "Alpha", SalesSource(provider=good_provider))
    assert await resolve_sales_dataset("CA", "Alpha", 1.0, 2.0, 3.0) == (
        "https://provider/layer/0",
        ["price", "date"],
    )

    # A provider failure resolves to None so find_comparables falls back to Hub.
    register_sales_source("CA", "Beta", SalesSource(provider=bad_provider))
    assert await resolve_sales_dataset("CA", "Beta", 1.0, 2.0, 3.0) is None
