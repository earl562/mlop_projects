"""Tests for the composite by-right trust gate (`pipeline/trust.py`).

The gate previously lived inline in `api/chat.py`, which meant only the chat and
harness transports applied it while the SSE `/analyze` route used a weaker test of
its own. These tests pin both the verdict logic and the cross-transport agreement
that motivated extracting it.
"""

from __future__ import annotations

from plotlot.core.types import (
    DensityAnalysis,
    ExtractionVerification,
    PropertyRecord,
    ZoningReport,
)
from plotlot.pipeline.trust import assess_by_right_trust
from plotlot.property.terrain import TerrainAnalysis


def _report(
    *,
    zoning_district: str = "RM-3-7",
    zoning_source: str = "gis",
    lot_source: str = "assessor",
    terrain: TerrainAnalysis | None = None,
    extraction_provisional: bool = False,
) -> ZoningReport:
    return ZoningReport(
        address="test",
        formatted_address="test",
        municipality="San Diego",
        county="San Diego",
        state="CA",
        zoning_district=zoning_district,
        zoning_source=zoning_source,
        property_record=PropertyRecord(lot_size_sqft=7710.0, lot_size_source=lot_source),
        density_analysis=DensityAnalysis(
            max_units=7, governing_constraint="min_lot_area", constraints=[], lot_size_sqft=7710.0
        ),
        extraction_verification=ExtractionVerification(
            fields=[], overall="verified", offer_is_provisional=extraction_provisional
        ),
        terrain=terrain,
    )


def _terrain(*, constrained: bool) -> TerrainAnalysis:
    return TerrainAnalysis(
        mean_slope_pct=43.0 if constrained else 4.0,
        max_slope_pct=71.0 if constrained else 7.0,
        elevation_min_ft=310.0,
        elevation_max_ft=448.0 if constrained else 315.0,
        elevation_differential_ft=138.0 if constrained else 5.0,
        steep_fraction=1.0 if constrained else 0.0,
        sample_count=64,
        is_steep_hillside=constrained,
        slope_constrained=constrained,
    )


def test_everything_confirmed_is_verified():
    trust = assess_by_right_trust(_report(terrain=_terrain(constrained=False)))
    assert trust.verification == "verified"
    assert trust.is_provisional is False
    assert trust.reasons == ()
    assert trust.buildable_area_confirmed is True


def test_geometry_lot_alone_makes_the_count_provisional():
    """The ordinance rule can verify perfectly and the count still not be firm —
    it was divided into an estimated lot area."""
    trust = assess_by_right_trust(_report(lot_source="geometry"))
    assert trust.is_provisional is True
    assert trust.zoning_confirmed is True
    assert any("legal lot" in r for r in trust.reasons)
    assert any("GIS polygon estimate" in r for r in trust.reasons)


def test_undetermined_district_makes_the_count_provisional():
    trust = assess_by_right_trust(_report(zoning_district="", zoning_source=""))
    assert trust.is_provisional is True
    assert trust.zoning_confirmed is False
    assert any("NOT read from a GIS layer" in r for r in trust.reasons)


def test_a_district_without_gis_provenance_reports_unconfirmed():
    """A district string is not evidence; its provenance is.

    This state is legacy-only — since `2a2f71c` the pipeline reports no district at
    all rather than an ordinance-inferred one, so `zoning_district` is non-empty only
    when a GIS layer supplied it. It survives in cached payloads, where the district
    must still read as UNCONFIRMED. Note it does not currently *gate*: gating keys off
    whether a district was determined at all, which preserves the pre-existing
    behaviour rather than silently downgrading old sessions."""
    trust = assess_by_right_trust(_report(zoning_district="R-7", zoning_source="ordinance"))
    assert trust.zoning_confirmed is False
    assert trust.zoning_determined is True


def test_measured_steep_slope_makes_the_count_an_upper_bound():
    trust = assess_by_right_trust(_report(terrain=_terrain(constrained=True)))
    assert trust.is_provisional is True
    assert trust.slope_measured is True
    assert trust.buildable_area_confirmed is False
    assert any("UPPER BOUND" in r for r in trust.reasons)


def test_unmeasured_slope_does_not_make_the_count_provisional():
    """Terrain is best-effort and the SSE path does not measure it at all. Treating
    "unknown" as "constrained" would flag nearly every report for no evidence."""
    trust = assess_by_right_trust(_report(terrain=None))
    assert trust.slope_measured is False
    assert trust.is_provisional is False
    assert not any("UPPER BOUND" in r for r in trust.reasons)


def test_unmeasured_slope_is_not_reported_as_confirmed_buildable_area():
    """...but it must not be laundered into a positive assertion either. Nobody
    checked, so `buildable_area_confirmed` is False while `slope_measured` explains
    why — the two are different facts and the payload keeps them separate."""
    trust = assess_by_right_trust(_report(terrain=None))
    assert trust.buildable_area_confirmed is False
    assert trust.slope_measured is False


def test_reasons_accumulate_across_independent_gates():
    trust = assess_by_right_trust(
        _report(
            zoning_district="",
            zoning_source="",
            lot_source="geometry",
            terrain=_terrain(constrained=True),
            extraction_provisional=True,
        )
    )
    assert len(trust.reasons) == 4
    assert trust.verification == "provisional"


def test_chat_payload_and_sse_route_reach_the_same_verdict():
    """The regression this module exists to prevent.

    `_format_grounded_analysis` (chat + MCP + CLI) and the SSE `/analyze` route must
    agree about whether a count is firm. They previously did not: the route tested
    only `extraction_verification.offer_is_provisional`, so this parcel — geometry
    lot, no GIS district — was PROVISIONAL in chat and firm in the browser."""
    from plotlot.api.chat import _format_grounded_analysis

    report = _report(zoning_district="", zoning_source="", lot_source="geometry")
    assert report.extraction_verification is not None
    assert report.extraction_verification.offer_is_provisional is False  # the weak test

    payload_verdict = _format_grounded_analysis(report)["by_right"]["verification"]
    route_verdict = assess_by_right_trust(report).verification

    assert payload_verdict == route_verdict == "provisional"
