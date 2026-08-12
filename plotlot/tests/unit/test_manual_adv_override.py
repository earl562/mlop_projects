"""A hand-supplied exit value must reach the residual — and be labelled as the
user's, not as evidence.

Automated comps are genuinely unavailable in some markets: no free California
sold-price layer exists, so a San Diego exit value is a labelled regional default
unless a keyed provider is live. `calculate_land_pro_forma` has always accepted an
`adv_per_unit` override, but nothing could reach it — it was not a request field on
any transport, so an analyst who comped by hand could only eyeball their number
against ours. These tests pin the wiring and, more importantly, the labelling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import (
    CompAnalysis,
    DensityAnalysis,
    ExtractionVerification,
    PropertyRecord,
    ZoningReport,
)
from plotlot.pipeline.grounding import _format_grounded_analysis
from plotlot.pipeline.proforma import calculate_land_pro_forma


def _density(units: int = 7) -> DensityAnalysis:
    return DensityAnalysis(
        max_units=units,
        governing_constraint="min_lot_area",
        constraints=[],
        lot_size_sqft=7710.0,
        confidence="high",
    )


def test_override_beats_both_comps_and_the_regional_default():
    """Precedence is the whole point: the user's number wins."""
    comps = CompAnalysis()
    comps.adv_per_unit = 420_000.0
    comps.adv_source = "comps"

    pf = calculate_land_pro_forma(density=_density(), comps=comps, adv_per_unit=900_000.0)

    assert pf.adv_per_unit == 900_000.0
    assert pf.adv_source == "override"
    assert pf.gross_development_value == pytest.approx(7 * 900_000.0)


def test_payload_attributes_the_number_to_the_user_not_to_plotlot():
    """The labelling requirement. A user's own figure echoed back as a PlotLot comp
    would be the worst kind of false grounding — it looks like corroboration."""
    report = ZoningReport(
        address="test",
        formatted_address="test",
        municipality="San Diego",
        county="San Diego",
        state="CA",
        zoning_district="RM-3-7",
        zoning_source="gis",
        property_record=PropertyRecord(lot_size_sqft=7710.0, lot_size_source="assessor"),
        density_analysis=_density(),
        extraction_verification=ExtractionVerification(
            fields=[], overall="verified", offer_is_provisional=False
        ),
    )
    report.pro_forma = calculate_land_pro_forma(density=_density(), adv_per_unit=900_000.0)

    valuation = _format_grounded_analysis(report)["valuation"]
    assert valuation["adv_source"] == "override"
    basis = valuation["adv_basis"]
    assert "SUPPLIED BY THE USER" in basis
    assert "never cite it as a PlotLot comp" in basis


def test_regional_default_basis_names_the_reason_it_fell_back():
    """The other half of the same honesty problem: when we DID fall back, say why.
    A dead provider and an uncovered market both land on the regional default."""
    comps = CompAnalysis()
    comps.notes = [
        "No open sales dataset for San Diego County, CA; RentCast refused the request "
        "(HTTP 403: billing/subscription-inactive). Exit value falls back to the "
        "labeled regional default."
    ]
    report = ZoningReport(
        address="test",
        formatted_address="test",
        municipality="San Diego",
        county="San Diego",
        state="CA",
        zoning_district="RM-3-7",
        zoning_source="gis",
        property_record=PropertyRecord(lot_size_sqft=7710.0, lot_size_source="assessor"),
        density_analysis=_density(),
        comp_analysis=comps,
    )
    from plotlot.pipeline.cost_model import get_cost_model

    report.pro_forma = calculate_land_pro_forma(
        density=_density(), comps=comps, cost_model=get_cost_model("CA", "San Diego")
    )

    basis = _format_grounded_analysis(report)["valuation"]["adv_basis"]
    assert "regional market default" in basis
    assert "billing/subscription-inactive" in basis


class TestHarnessHandlerWiring:
    @pytest.mark.asyncio
    async def test_handler_passes_the_override_through(self):
        from plotlot.harness.default_runtime import _handle_analyze_property
        from plotlot.land_use.models import ToolContext

        ctx = ToolContext(workspace_id="ws", actor_user_id="u", run_id="r")
        deep = AsyncMock(return_value=None)
        with patch("plotlot.pipeline.analyze.analyze_property_deep", new=deep):
            await _handle_analyze_property(
                {"address": "1233 Hueneme St", "adv_per_unit": 900000}, ctx
            )
        deep.assert_awaited_once_with("1233 Hueneme St", adv_per_unit=900000.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -5, "abc", None])
    async def test_unusable_override_falls_back_instead_of_failing(self, bad):
        """A bad override should degrade to the normal comps path, not blow up an
        otherwise valid analysis."""
        from plotlot.harness.default_runtime import _handle_analyze_property
        from plotlot.land_use.models import ToolContext

        ctx = ToolContext(workspace_id="ws", actor_user_id="u", run_id="r")
        deep = AsyncMock(return_value=None)
        with patch("plotlot.pipeline.analyze.analyze_property_deep", new=deep):
            result = await _handle_analyze_property(
                {"address": "1233 Hueneme St", "adv_per_unit": bad}, ctx
            )
        deep.assert_awaited_once_with("1233 Hueneme St", adv_per_unit=None)
        assert result["status"] == "not_found"  # not "error"

    def test_contract_advertises_the_parameter(self):
        from plotlot.harness.tool_registry import get_tool_contract

        props = get_tool_contract("analyze_property").input_schema["properties"]
        assert "adv_per_unit" in props
        assert props["adv_per_unit"]["exclusiveMinimum"] == 0
        # Still optional — the normal path must not require it.
        assert get_tool_contract("analyze_property").input_schema["required"] == ["address"]
