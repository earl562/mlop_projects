"""Tests for batch buy-box screening (pure eval + async orchestration)."""

import asyncio

from plotlot.core.types import (
    DensityAnalysis,
    ExtractionVerification,
    LandProForma,
    PropertyRecord,
    SiteRisk,
    ZoningReport,
)
from plotlot.pipeline.screening import (
    BuyBox,
    evaluate_buy_box,
    screen_addresses,
    screen_reports,
)


def _report(
    address="1 Main St",
    state="CA",
    county="San Diego",
    zoning="RM-3-9",
    lot_sqft=10_000.0,
    max_units=12,
    residual=900_000.0,
    provisional=False,
    flood="low",
) -> ZoningReport:
    return ZoningReport(
        address=address,
        formatted_address=address,
        municipality="San Diego",
        county=county,
        state=state,
        zoning_district=zoning,
        property_record=PropertyRecord(lot_size_sqft=lot_sqft),
        density_analysis=DensityAnalysis(
            max_units=max_units, governing_constraint="density", constraints=[]
        ),
        pro_forma=LandProForma(max_units=max_units, max_land_price=residual),
        extraction_verification=ExtractionVerification(offer_is_provisional=provisional),
        site_risk=SiteRisk(overall_risk=flood),
    )


class TestEvaluateBuyBox:
    def test_passes_all_criteria(self):
        bb = BuyBox(
            states=["CA"],
            counties=["San Diego"],
            zoning_prefixes=["RM"],
            min_lot_sqft=5_000,
            max_lot_sqft=20_000,
            min_units=10,
            min_residual=500_000,
        )
        r = evaluate_buy_box(_report(), bb)
        assert r.status == "qualified"
        assert r.reasons == []
        assert r.score == 900_000.0

    def test_wrong_state_rejected(self):
        r = evaluate_buy_box(_report(state="TX"), BuyBox(states=["CA"]))
        assert r.status == "rejected"
        assert any("State" in x for x in r.reasons)

    def test_county_case_insensitive_and_suffix(self):
        r = evaluate_buy_box(_report(county="San Diego County"), BuyBox(counties=["san diego"]))
        assert r.status == "qualified"

    def test_zoning_prefix_mismatch(self):
        r = evaluate_buy_box(_report(zoning="C-2"), BuyBox(zoning_prefixes=["RM", "RD"]))
        assert any("Zoning" in x for x in r.reasons)

    def test_lot_size_bounds(self):
        assert (
            evaluate_buy_box(_report(lot_sqft=3_000), BuyBox(min_lot_sqft=5_000)).status
            == "rejected"
        )
        assert (
            evaluate_buy_box(_report(lot_sqft=99_000), BuyBox(max_lot_sqft=20_000)).status
            == "rejected"
        )

    def test_min_units(self):
        assert evaluate_buy_box(_report(max_units=4), BuyBox(min_units=10)).status == "rejected"

    def test_min_residual(self):
        assert (
            evaluate_buy_box(_report(residual=100_000), BuyBox(min_residual=500_000)).status
            == "rejected"
        )

    def test_high_flood_excluded(self):
        r = evaluate_buy_box(_report(flood="high"), BuyBox(exclude_high_flood_risk=True))
        assert any("flood" in x.lower() for x in r.reasons)

    def test_require_verified_drops_provisional(self):
        r = evaluate_buy_box(_report(provisional=True), BuyBox(require_verified=True))
        assert any("provisional" in x.lower() for x in r.reasons)
        # Same deal qualifies if we don't require verification.
        assert evaluate_buy_box(_report(provisional=True), BuyBox()).status == "qualified"


class TestScreenReports:
    def test_ranks_qualified_by_residual_desc(self):
        reports = [
            _report(address="A", residual=300_000),
            _report(address="B", residual=900_000),
            _report(address="C", residual=600_000),
        ]
        batch = screen_reports(reports, BuyBox())
        assert [r.address for r in batch.qualified] == ["B", "C", "A"]
        assert batch.qualified_count == 3

    def test_max_results_caps(self):
        reports = [_report(address=f"A{i}", residual=i * 1000) for i in range(10)]
        batch = screen_reports(reports, BuyBox(max_results=3))
        assert len(batch.qualified) == 3
        assert batch.qualified[0].address == "A9"  # highest residual first

    def test_splits_qualified_and_rejected(self):
        reports = [_report(address="ok", max_units=12), _report(address="no", max_units=2)]
        batch = screen_reports(reports, BuyBox(min_units=10))
        assert [r.address for r in batch.qualified] == ["ok"]
        assert [r.address for r in batch.rejected] == ["no"]


class TestScreenAddresses:
    async def test_happy_path_ranks_and_callbacks(self):
        data = {
            "A": _report(address="A", residual=300_000),
            "B": _report(address="B", residual=900_000),
        }

        async def analyze(addr):
            return data[addr]

        seen: list[str] = []

        async def on_result(r):
            seen.append(r.address)

        batch = await screen_addresses(
            ["A", "B"], BuyBox(), analyze, concurrency=2, on_result=on_result
        )
        assert [r.address for r in batch.qualified] == ["B", "A"]
        assert sorted(seen) == ["A", "B"]

    async def test_none_and_exception_become_errors(self):
        async def analyze(addr):
            if addr == "none":
                return None
            if addr == "boom":
                raise RuntimeError("kaboom")
            return _report(address=addr)

        batch = await screen_addresses(["ok", "none", "boom"], BuyBox(), analyze)
        assert batch.qualified_count == 1
        assert {r.address for r in batch.errors} == {"none", "boom"}
        assert any("kaboom" in r.error for r in batch.errors)

    async def test_timeout_is_isolated(self):
        async def analyze(addr):
            if addr == "slow":
                await asyncio.sleep(1.0)
            return _report(address=addr)

        batch = await screen_addresses(["fast", "slow"], BuyBox(), analyze, per_item_timeout=0.05)
        errs = {r.address: r.error for r in batch.errors}
        assert errs.get("slow") == "timeout"
        assert batch.qualified_count == 1  # "fast" still processed

    async def test_respects_concurrency_limit(self):
        active = 0
        peak = 0

        async def analyze(addr):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return _report(address=addr)

        await screen_addresses([f"a{i}" for i in range(8)], BuyBox(), analyze, concurrency=2)
        assert peak <= 2
