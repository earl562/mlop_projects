"""WIRE-2.1b contract tests: _agentic_analysis emits typed Claims.

Pins the claim-emission wiring (criteria 1-5):
  * _agentic_analysis produces Claim objects for the zoning facts it extracts,
    returned alongside the ZoningReport via ``report.claims`` (criteria 1, 4).
  * A zoning.district Claim is kind=verified_fact / origin=local_authority when
    grounded in indexed ordinance text (or the GIS zone code); an ungrounded
    LLM district assertion is emitted under ``assumed_zoning.district`` with
    origin=unknown / kind=assumption — the Claim invariant forbids ``zoning.*``
    with a non-local-authority origin, so the ungrounded assertion lives under a
    distinct namespace rather than weakening the boundary (criterion 2).
  * A cost.* / financing.* Claim is never kind=verified_fact — the constructor
    raises, holding the boundary at the emission point (criterion 3).
  * Contract test: _agentic_analysis on a mocked ordinance input emits at least
    one zoning.district Claim with origin=local_authority (criterion 5).

The calculator/lookup wiring is in test_lookup.py / test_lookup_dimensional_standard.py;
this file covers the claim-emission seam specifically.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import CoastalHeightOverlay, PropertyRecord
from plotlot.domain.claims import Claim, ClaimKind, ClaimOrigin, SourceBoundaryViolation
from plotlot.pipeline.lookup import (
    _build_fallback_report,
    _extract_claims_from_report,
    lookup_address,
)
from plotlot.storage import dimensional_standards as ds_store


def _ftl_geo():
    return {
        "formatted_address": "101 SE 1st Ave, Fort Lauderdale, FL 33301",
        "municipality": "Fort Lauderdale",
        "county": "Broward",
        "state": "FL",
        "lat": 26.113,
        "lng": -80.144,
        "accuracy": 0.95,
    }


def _ftl_prop():
    r = PropertyRecord(county="Broward")
    r.municipality = "Fort Lauderdale"
    r.zoning_code = "RS-8"
    r.lot_size_sqft = 43560.0
    r.lot_dimensions = "100x435"
    r.lat = 26.113
    r.lng = -80.144
    return r


class _FakeOrdResult:
    """Minimal search-result shape with source provenance."""

    def __init__(self, source_url="https://ftl.gov/ord/zoning", zone_codes=None):
        self.source_url = source_url
        self.zone_codes = zone_codes or ["RS-8"]
        self.section = "Sec. 47-25"
        self.section_title = "RS-8 Single-Family Residential"
        self.chunk_text = "RS-8: max density 8 du/ac, front setback 25 ft."
        self.score = 0.9


def _submit_report_llm(district: str = "RS-8"):
    async def _mock(messages, tools=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "submit_report",
                        "arguments": json.dumps(
                            {
                                "zoning_district": district,
                                "zoning_description": "Single Family Residential",
                                "summary": "RS-8 single-family district.",
                                "confidence": "high",
                                "max_density_units_per_acre": 8.0,
                                "setback_front_ft": 25.0,
                                "property_type": "single_family",
                            }
                        ),
                    },
                }
            ],
        }

    return _mock


class TestClaimEmissionHelpers:
    """Direct tests of _extract_claims_from_report (criterion 2)."""

    def test_grounded_district_emits_zoning_district_verified_fact(self):
        args = {"zoning_district": "RS-8", "setback_front_ft": 25.0}
        claims = _extract_claims_from_report(args, [_FakeOrdResult()], _ftl_prop())
        district = next(c for c in claims if c.field_key == "zoning.district")
        assert district.kind is ClaimKind.VERIFIED_FACT
        assert district.origin is ClaimOrigin.LOCAL_AUTHORITY
        assert district.source_url == "https://ftl.gov/ord/zoning"

    def test_gis_code_alone_grounded(self):
        # No ordinance text, but the GIS zone code is a local-authority record.
        args = {"zoning_district": "RS-8"}
        claims = _extract_claims_from_report(args, None, _ftl_prop())
        district = next(c for c in claims if c.field_key == "zoning.district")
        assert district.kind is ClaimKind.VERIFIED_FACT
        assert district.origin is ClaimOrigin.LOCAL_AUTHORITY
        assert district.metadata["grounded_by"] == "gis_code"

    def test_ungrounded_llm_district_lives_under_assumed_zoning(self):
        # No ordinance text, no GIS code → LLM fallback. zoning.* forbids
        # origin=unknown, so the assertion is emitted under assumed_zoning.*
        # with origin=unknown / kind=assumption (confidence ≤ 0.5).
        args = {"zoning_district": "RS-8", "setback_front_ft": 25.0}
        claims = _extract_claims_from_report(args, None, PropertyRecord(county="Broward"))
        assert not any(c.field_key == "zoning.district" for c in claims)
        assumed = next(c for c in claims if c.field_key == "assumed_zoning.district")
        assert assumed.kind is ClaimKind.ASSUMPTION
        assert assumed.origin is ClaimOrigin.UNKNOWN
        assert assumed.confidence <= 0.5
        # standards.* (unconstrained namespace) carries origin=unknown too.
        std = next(c for c in claims if c.field_key == "standards.setback_front_ft")
        assert std.kind is ClaimKind.ASSUMPTION
        assert std.origin is ClaimOrigin.UNKNOWN

    def test_cost_claim_verified_fact_raises_at_emission_point(self):
        # Criterion 3: a cost.* / financing.* Claim is never kind=verified_fact.
        # The constructor enforces this at construction (emission point).
        with pytest.raises(SourceBoundaryViolation):
            Claim(
                field_key="cost.hard_per_sqft",
                value=150.0,
                kind=ClaimKind.VERIFIED_FACT,
                origin=ClaimOrigin.LOCAL_AUTHORITY,
            )
        with pytest.raises(SourceBoundaryViolation):
            Claim(
                field_key="financing.perm_rate",
                value=0.06,
                kind=ClaimKind.VERIFIED_FACT,
                origin=ClaimOrigin.LOCAL_AUTHORITY,
            )

    def test_no_cost_or_financing_claims_emitted_by_helper(self):
        # The helper only emits zoning.*/assumed_zoning.*/standards.* claims —
        # never cost.* or financing.* (those come from the pro-forma).
        args = {
            "zoning_district": "RS-8",
            "setback_front_ft": 25.0,
            "max_density_units_per_acre": 8.0,
        }
        claims = _extract_claims_from_report(args, [_FakeOrdResult()], _ftl_prop())
        namespaces = {c.namespace for c in claims}
        assert "cost" not in namespaces
        assert "financing" not in namespaces


class TestAgenticAnalysisEmitsClaims:
    """End-to-end: _agentic_analysis (via lookup_address) populates report.claims
    (criteria 1, 4, 5)."""

    @pytest.mark.asyncio
    async def test_mocked_ordinance_input_emits_local_authority_district_claim(self):
        """Criterion 5: _agentic_analysis on a mocked ordinance input emits at
        least one zoning.district Claim with origin=local_authority."""
        from plotlot.pipeline import lookup as lookup_mod

        lookup_mod._pipeline_cache.clear()
        ds_store.clear_dimensional_standard_fixtures()
        ds_store._ensure_seeded()

        with ExitStack() as stack:
            stack.enter_context(
                patch("plotlot.pipeline.lookup.geocode_address", return_value=_ftl_geo())
            )
            stack.enter_context(
                patch("plotlot.pipeline.lookup.lookup_property", return_value=_ftl_prop())
            )
            stack.enter_context(
                patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_FakeOrdResult()])
            )
            stack.enter_context(
                patch("plotlot.pipeline.lookup.get_session", return_value=AsyncMock())
            )
            stack.enter_context(
                patch("plotlot.retrieval.llm.call_llm", side_effect=_submit_report_llm())
            )
            stack.enter_context(
                patch(
                    "plotlot.pipeline.coastal_overlay.fetch_coastal_height_overlay",
                    new_callable=AsyncMock,
                    return_value=CoastalHeightOverlay(status="not_applicable"),
                )
            )
            report = await lookup_address("101 SE 1st Ave, Fort Lauderdale, FL 33301")

        assert report is not None
        assert report.claims, "_agentic_analysis must emit claims (criterion 1)"
        district_claims = [c for c in report.claims if c.field_key == "zoning.district"]
        assert district_claims, "a zoning.district claim must be emitted (criterion 5)"
        assert all(c.origin is ClaimOrigin.LOCAL_AUTHORITY for c in district_claims)
        assert all(c.kind is ClaimKind.VERIFIED_FACT for c in district_claims)

    @pytest.mark.asyncio
    async def test_fallback_report_carries_grounded_district_claim(self):
        """The fallback path (LLM didn't submit) still emits a grounded
        zoning.district claim when a GIS code is present."""
        prop = _ftl_prop()
        report = _build_fallback_report(
            "101 SE 1st Ave, Fort Lauderdale, FL 33301",
            _ftl_geo(),
            prop,
            ["https://ftl.gov/ord"],
            search_results=[_FakeOrdResult()],
        )
        district = next(c for c in report.claims if c.field_key == "zoning.district")
        assert district.kind is ClaimKind.VERIFIED_FACT
        assert district.origin is ClaimOrigin.LOCAL_AUTHORITY
