"""Tests for the chat `analyze_property` grounding tool.

This tool is the anti-hallucination fix for the conversational agent: instead of
free-forming density, comps, fees, and flood zones (which produced the wrong
"RM-3-7 = 7 units/acre", fake North Park comps, and "assumed Zone X" answers),
the agent must call `analyze_property` and cite ONLY its grounded output.

These tests lock in: the grounded payload shape, the provisional vs verified
signalling, error handling, tool registration, and the system-prompt gate.
"""

from __future__ import annotations

import json

import pytest

from plotlot.api import chat as chat_mod
from plotlot.api.chat import (
    CHAT_TOOLS,
    CORE_TOOLS,
    GROUNDING_POLICY,
    _build_active_analysis_context,
    _execute_analyze_property,
    _execute_screen_properties,
    _format_grounded_analysis,
)
from plotlot.core.types import (
    CoastalHeightOverlay,
    CompAnalysis,
    DensityAnalysis,
    DensityUplift,
    EntitlementAssessment,
    ExtractionVerification,
    FieldVerification,
    FloodZoneInfo,
    LandProForma,
    PropertyRecord,
    SensitivityTable,
    SiteRisk,
    UpliftProgram,
    ZoningReport,
)
from plotlot.harness.tool_registry import tool_exists
from plotlot.pipeline.screening import BatchScreeningResult, ScreeningResult


@pytest.fixture(autouse=True)
def _isolate_fee_registry():
    """Run formatter tests against an empty fee registry so the module-level San
    Diego schedule doesn't leak in. Tests that need a schedule register it
    explicitly; this keeps the coarse-aggregate path deterministic."""
    from plotlot.pipeline import fee_schedule as _fs

    saved = dict(_fs._FEE_SCHEDULES)
    _fs._FEE_SCHEDULES.clear()
    yield
    _fs._FEE_SCHEDULES.clear()
    _fs._FEE_SCHEDULES.update(saved)


def _hueneme_report(*, provisional: bool = False) -> ZoningReport:
    """A representative grounded report for the 1233 Hueneme St regression case."""
    return ZoningReport(
        address="1233 Hueneme St, San Diego, CA 92110",
        formatted_address="1233 Hueneme St, San Diego, CA 92110",
        municipality="San Diego",
        county="San Diego",
        state="CA",
        lat=32.75,
        lng=-117.21,
        zoning_district="RM-3-7",
        zoning_description="Residential Multiple-Unit",
        property_record=PropertyRecord(
            zoning_code="RM-3-7", lot_size_sqft=6470.61, lat=32.75, lng=-117.21
        ),
        density_analysis=DensityAnalysis(
            max_units=6,
            governing_constraint="min_lot_area",
            constraints=[],
            lot_size_sqft=6470.61,
            confidence="high",
        ),
        extraction_verification=ExtractionVerification(
            fields=[
                FieldVerification(
                    field="min_lot_area_per_unit_sqft",
                    label="Min lot area per unit (sqft)",
                    llm_value=1000.0,
                    source_value=1000.0,
                    status="verified",
                    citation="RM-3-7 permits a maximum density of 1 dwelling unit "
                    "for each 1,000 square feet of lot area",
                    section="131.0406",
                ),
            ],
            overall="verified",
            offer_is_provisional=provisional,
        ),
        comp_analysis=CompAnalysis(
            estimated_land_value=1_200_000.0,
            estimated_land_value_low=1_000_000.0,
            estimated_land_value_high=1_400_000.0,
            adv_per_unit=420_000.0,
            adv_source="comps",
            confidence=0.62,
        ),
        pro_forma=LandProForma(
            max_land_price=980_000.0,
            gross_development_value=2_520_000.0,
            impact_fees_per_unit=18_000.0,
            construction_cost_psf=275.0,
            adv_per_unit=420_000.0,
            adv_source="comps",
            market="San Diego",
            max_units=6,
        ),
        entitlement=EntitlementAssessment(
            path="by_right",
            complexity="low",
            est_timeline_months=8.0,
            impact_fee_per_unit=18_000.0,
            impact_fees_total=108_000.0,
            utilities_note="Utility capacity not verified at parcel.",
        ),
        site_risk=SiteRisk(
            flood_zone=FloodZoneInfo(
                zone="X",
                zone_subtype="AREA OF MINIMAL FLOOD HAZARD",
                in_sfha=False,
                risk_level="minimal",
                description="Minimal flood hazard.",
            ),
            has_wetlands=False,
            overall_risk="low",
            data_sources=["FEMA NFHL", "USFWS NWI"],
        ),
        density_uplift=DensityUplift(
            base_units=6,
            state="CA",
            max_potential_units=12,
            programs=[
                UpliftProgram(
                    name="ADU/JADU",
                    statute="Gov. Code 65852.2",
                    eligibility="eligible",
                    additional_units=2,
                    potential_units=8,
                ),
            ],
        ),
        sensitivity=SensitivityTable(
            row_label="Construction $/sf",
            col_label="ADV per Unit",
            row_values=[280.0, 350.0, 420.0],  # -20%, base, +20%
            col_values=[336_000.0, 420_000.0, 504_000.0],  # -20%, base, +20%
            grid=[
                [1_200_000.0, 1_400_000.0, 1_600_000.0],  # construction -20%
                [600_000.0, 980_000.0, 1_360_000.0],  # base construction
                [-200_000.0, 380_000.0, 960_000.0],  # construction +20%
            ],
            base_row_index=1,
            base_col_index=1,
            base_value=980_000.0,
        ),
    )


def test_grounded_payload_has_verified_units_and_drivers():
    payload = _format_grounded_analysis(_hueneme_report())
    assert payload["status"] == "success"
    assert payload["zoning_code"] == "RM-3-7"
    assert payload["lot_size_sqft"] == 6471  # rounded
    by_right = payload["by_right"]
    assert by_right["max_units"] == 6
    assert by_right["governing_constraint"] == "min_lot_area"
    assert by_right["verification"] == "verified"
    assert by_right["offer_is_provisional"] is False
    # The verified driver carries its source value + citation (the grounding proof).
    driver = by_right["verified_drivers"][0]
    assert driver["status"] == "verified"
    assert driver["source_value"] == 1000.0
    assert "1,000 square feet" in driver["citation"]


def test_grounded_payload_marks_provisional_when_flagged():
    payload = _format_grounded_analysis(_hueneme_report(provisional=True))
    assert payload["by_right"]["verification"] == "provisional"
    assert payload["by_right"]["offer_is_provisional"] is True


def test_grounded_payload_surfaces_valuation_fees_risk_entitlement():
    payload = _format_grounded_analysis(_hueneme_report())

    val = payload["valuation"]
    assert val["estimated_land_value"] == 1_200_000
    assert val["land_value_range"] == [1_000_000, 1_400_000]
    assert val["max_land_price_residual"] == 980_000
    assert val["adv_per_unit"] == 420_000
    assert val["adv_source"] == "comps"
    assert val["impact_fees_per_unit"] == 18_000
    assert "impact_fees_basis" in val  # labeled coarse aggregate, not itemizable
    assert "coarse regional aggregate" in val["impact_fees_basis"]
    assert "impact_fee_breakdown" not in val  # no real schedule registered
    assert val["market"] == "San Diego"

    assert payload["entitlement"]["path"] == "by_right"
    assert payload["entitlement"]["est_timeline_months"] == 8.0

    risk = payload["site_risk"]
    assert risk["flood_zone"] == "X"
    assert risk["in_special_flood_hazard_area"] is False
    assert risk["has_wetlands"] is False

    upside = payload["ca_upside"]
    assert upside["base_units"] == 6
    assert upside["max_potential_units"] == 12
    assert upside["programs"][0]["statute"] == "Gov. Code 65852.2"

    # The payload always reminds the model not to invent numbers.
    assert "grounding_note" in payload
    assert "not available" in payload["grounding_note"].lower()


def test_regional_default_adv_is_labeled_an_estimate():
    report = _hueneme_report()
    # No comps found → residual falls back to the regional-default ADV.
    report.comp_analysis = None
    report.pro_forma.adv_source = "regional_default"
    payload = _format_grounded_analysis(report)
    val = payload["valuation"]
    assert val["adv_source"] == "regional_default"
    assert "adv_basis" in val
    assert "estimate" in val["adv_basis"].lower()


def test_policy_forbids_itemizing_fee_aggregates():
    policy = GROUNDING_POLICY.lower()
    assert "decompose" in policy or "itemize" in policy
    assert "fire" in policy and "police" in policy  # the fabricated categories
    assert "coarse" in policy


def test_fee_breakdown_emitted_only_when_real_schedule_registered():
    from plotlot.pipeline import fee_schedule
    from plotlot.pipeline.fee_schedule import FeeComponent, FeeSchedule, register_fee_schedule

    report = _hueneme_report()  # state CA, county San Diego

    # No schedule registered → coarse aggregate, no breakdown, "do not itemize".
    payload = _format_grounded_analysis(report)
    assert "impact_fee_breakdown" not in payload["valuation"]
    assert "line items" in payload["valuation"]["impact_fees_basis"]

    before = dict(fee_schedule._FEE_SCHEDULES)
    try:
        register_fee_schedule(
            FeeSchedule(
                jurisdiction="City of San Diego",
                state="CA",
                source="FY26 Fee Schedule",
                effective_date="2025-07-01",
                components=(
                    FeeComponent("Citywide Mobility DIF", 9000.0, "R-314273"),
                    FeeComponent("Citywide Fire-Rescue DIF", 4000.0, "R-314271"),
                ),
            ),
            county="San Diego",
        )
        payload = _format_grounded_analysis(report)
        val = payload["valuation"]
        assert val["impact_fees_per_unit"] == 13000  # itemized total
        assert len(val["impact_fee_breakdown"]) == 2
        assert val["impact_fee_breakdown"][0]["citation"] == "R-314273"
        assert "itemized from" in val["impact_fees_basis"]
    finally:
        fee_schedule._FEE_SCHEDULES.clear()
        fee_schedule._FEE_SCHEDULES.update(before)


def test_partial_fee_schedule_itemizes_but_keeps_conservative_residual():
    """A partial schedule (covers_all_fees=False, e.g. SD city DIFs only) itemizes
    the verified line items for display but must NOT lower the residual fee — the
    all-in stays conservative because RTCIP/school/utility are not itemized."""
    from plotlot.pipeline.fee_schedule import FeeComponent, FeeSchedule, register_fee_schedule

    report = _hueneme_report()  # pro_forma.impact_fees_per_unit = 18_000 (conservative)
    register_fee_schedule(
        FeeSchedule(
            jurisdiction="City of San Diego",
            state="CA",
            source="FY26 Citywide DIFs",
            effective_date="2025-07-01",
            covers_all_fees=False,
            components=(
                FeeComponent("Citywide Park DIF", 15438.0, "Parks for All of Us"),
                FeeComponent("Citywide Mobility DIF", 4627.0, "R-314273"),
            ),
        ),
        county="San Diego",
    )
    val = _format_grounded_analysis(report)["valuation"]

    # Verified DIFs are itemized for display...
    assert len(val["impact_fee_breakdown"]) == 2
    assert val["itemized_city_dif_per_unit"] == 20065  # 15438 + 4627
    # ...but the residual fee stays the conservative all-in (not the partial DIF total).
    assert val["impact_fees_per_unit"] == 18_000
    assert "conservative" in val["impact_fees_basis"].lower()
    assert "separate" in val["impact_fees_basis"].lower()


def test_grounded_payload_handles_missing_density_gracefully():
    report = _hueneme_report()
    report.density_analysis = None
    payload = _format_grounded_analysis(report)
    assert payload["by_right"] is None
    assert "note" in payload


# ---------------------------------------------------------------------------
# Deterministic trust pass — the NIM narrator ignores correctly-injected fields
# and misreads labeled ones, so the high-stakes facts are made deterministic.
# ---------------------------------------------------------------------------


def test_source_query_detection():
    from plotlot.api.chat import _is_source_query

    # Source / trust / citation phrasings fire.
    assert _is_source_query("Can I trust that unit count — what's the source?")
    assert _is_source_query("what's the source?")
    assert _is_source_query("how do you know that?")
    assert _is_source_query("cite the ordinance")
    assert _is_source_query("what code says that?")
    # Ordinary analysis questions do NOT hijack the source short-circuit.
    assert not _is_source_query("what is the maximum buildable unit")
    assert not _is_source_query("how many units can I build by-right?")
    assert not _is_source_query("generate a pro forma")


def test_source_answer_echoes_verified_citation_never_fabricates():
    from plotlot.api.chat import _build_source_answer

    payload = _format_grounded_analysis(_hueneme_report())
    answer = _build_source_answer(payload)
    assert answer is not None
    # Reproduces the EXACT verified ordinance sentence + the real section.
    assert "1,000 square feet of lot area" in answer
    assert "131.0406" in answer  # the verified driver's real section
    assert "VERIFIED" in answer
    assert "6 units" in answer
    # Never the fabricated section the narrator invented from the FAR field.
    assert "131.0445" not in answer


def test_source_answer_none_when_no_verified_driver():
    """Provisional / unverified → fall through to the model (no fabricated echo)."""
    from plotlot.api.chat import _build_source_answer

    report = _hueneme_report(provisional=True)
    # Only a conflicting driver — nothing verified to echo.
    report.extraction_verification.fields = [
        FieldVerification(
            field="far",
            label="Floor area ratio",
            llm_value=1.5,
            source_value=4.0,
            status="conflict",
            citation="…[See Section 131.0445(a)] applies Max floor area ratio…",
            section="Art.01 Div.04",
        ),
    ]
    payload = _format_grounded_analysis(report)
    assert _build_source_answer(payload) is None


def test_source_answer_does_not_borrow_a_conflicting_fields_section():
    """The FAR conflict citation contains '131.0445' — it must never be echoed."""
    from plotlot.api.chat import _build_source_answer

    report = _hueneme_report()
    # Verified min-lot driver PLUS a conflicting FAR driver whose citation holds the
    # section the narrator previously mis-attributed to the unit count.
    report.extraction_verification.fields.append(
        FieldVerification(
            field="far",
            label="Floor area ratio",
            status="conflict",
            source_value=4.0,
            citation="…rage for sloping lots [See Section 131.0445(a)] applies…",
            section="Art.01 Div.04",
        )
    )
    answer = _build_source_answer(_format_grounded_analysis(report))
    assert answer is not None
    assert "131.0445" not in answer
    assert "1,000 square feet of lot area" in answer


def test_exit_value_formula_is_per_unit_and_unambiguous():
    payload = _format_grounded_analysis(_hueneme_report())
    formula = payload["valuation"]["exit_value_formula"]
    # units × ADV-per-unit = GDV, with an explicit "per unit" guard.
    assert "6 units" in formula
    assert "$420,000/unit" in formula
    assert "$2,520,000" in formula  # 6 × 420k GDV, never 420k/6
    assert "PER UNIT" in formula


def test_active_context_exit_line_unambiguous():
    payload = _format_grounded_analysis(_hueneme_report())
    block = _build_active_analysis_context(payload)
    assert "Exit value:" in block
    assert "$2,520,000" in block
    assert "do not divide" in block.lower() or "never divide" in block.lower()


def test_sensitivity_surfaced_with_labeled_scenarios():
    payload = _format_grounded_analysis(_hueneme_report())
    sens = payload["sensitivity"]
    assert sens["base_max_land_price"] == 980_000
    joined = " | ".join(sens["scenarios"])
    # Percentage-labeled moves off the base case.
    assert "Construction +20%" in joined
    assert "Exit -20%" in joined
    # Negative cells are flagged so the narrator can say "does not pencil".
    assert "does not pencil" in joined


def test_active_context_includes_sensitivity_scenarios():
    payload = _format_grounded_analysis(_hueneme_report())
    block = _build_active_analysis_context(payload)
    assert "Sensitivity" in block
    assert "Construction +20%" in block
    assert "do NOT invent" in block


def test_active_context_lists_real_upside_programs_only():
    payload = _format_grounded_analysis(_hueneme_report())
    block = _build_active_analysis_context(payload)
    # The real program + statute are present; the narrator is told not to invent.
    assert "ADU/JADU" in block
    assert "Gov. Code 65852.2" in block
    assert "SB9" in block  # appears only inside the "do NOT invent ... no 'SB9'" guard


def test_internal_reconciliation_warnings_are_filtered_out():
    report = _hueneme_report()
    internal = "Max density (units/acre): Extracted 6 u/ac contradicts source min lot area."
    user_facing = "ADV per unit is a regional market estimate, not local sold-unit comps."
    report.extraction_verification.warnings = [internal]
    report.warnings = [internal, user_facing]
    payload = _format_grounded_analysis(report)
    assert payload["warnings"] == [user_facing]  # internal diagnostic dropped


def test_policy_states_deterministic_field_rules():
    policy = GROUNDING_POLICY
    low = policy.lower()
    # Citation rule (with the exact fabricated section called out).
    assert "131.0445" in policy
    # Exit/GDV rule.
    assert "per unit" in low and "divide" in low
    # Sensitivity rule.
    assert "sensitivity" in low
    # Program rule (the invented program names).
    assert "sb9" in low or "educationally impactful" in low


@pytest.mark.asyncio
async def test_execute_requires_address():
    out = json.loads(await _execute_analyze_property("   "))
    assert out["status"] == "error"


@pytest.mark.asyncio
async def test_execute_returns_not_found_when_pipeline_returns_none(monkeypatch):
    async def _none(_address):
        return None

    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_deep", _none)
    out = json.loads(await _execute_analyze_property("nowhere"))
    assert out["status"] == "not_found"


@pytest.mark.asyncio
async def test_execute_formats_grounded_report_and_sets_context(monkeypatch):
    report = _hueneme_report()

    async def _report(_address):
        return report

    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_deep", _report)
    out = json.loads(
        await _execute_analyze_property("1233 Hueneme St, San Diego, CA 92110", session_id="s1")
    )
    assert out["status"] == "success"
    assert out["by_right"]["max_units"] == 6
    # Session context is populated for downstream document generation.
    ctx = chat_mod._sessions.get_property_context("s1")
    assert ctx is not None
    assert ctx["zoning_code"] == "RM-3-7"
    assert ctx["state"] == "CA"


@pytest.mark.asyncio
async def test_execute_handles_pipeline_exception(monkeypatch):
    async def _boom(_address):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_deep", _boom)
    out = json.loads(await _execute_analyze_property("123 Main St"))
    assert out["status"] == "error"


def test_tool_is_registered_and_core():
    names = {t["function"]["name"] for t in CHAT_TOOLS}
    assert "analyze_property" in names
    core_names = {t["function"]["name"] for t in CORE_TOOLS}
    assert "analyze_property" in core_names


def test_grounding_policy_forbids_freeforming_numbers():
    policy = GROUNDING_POLICY.lower()
    assert "analyze_property" in policy
    assert "screen_properties" in policy  # the batch / many-parcels path
    # It must explicitly forbid the failure modes the audit found.
    assert "rm-3-7" in policy  # the zone-name-as-density trap
    assert "provisional" in policy
    assert "benchmark" in policy or "training" in policy


def test_grounded_payload_surfaces_coastal_overlay_when_present():
    report = _hueneme_report()
    report.coastal_overlay = CoastalHeightOverlay(
        applies=True,
        height_limit_ft=30.0,
        status="in",
        zone_name="Coastal Height Limitation Overlay Zone",
        citation="SDMC 132.0505 (Proposition D)",
    )
    payload = _format_grounded_analysis(report)
    assert payload["coastal_height_overlay"]["applies"] is True
    assert payload["coastal_height_overlay"]["height_limit_ft"] == 30.0
    assert payload["coastal_height_overlay"]["status"] == "in"


def test_grounded_payload_omits_coastal_when_not_applicable():
    report = _hueneme_report()
    report.coastal_overlay = CoastalHeightOverlay(status="not_applicable")
    payload = _format_grounded_analysis(report)
    assert "coastal_height_overlay" not in payload


# ---------------------------------------------------------------------------
# Batch screening tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_requires_addresses():
    out = json.loads(await _execute_screen_properties({"addresses": []}))
    assert out["status"] == "error"


@pytest.mark.asyncio
async def test_screen_ranks_qualified_and_grounds(monkeypatch):
    batch = BatchScreeningResult(
        qualified=[
            ScreeningResult(
                address="1233 Hueneme St",
                status="qualified",
                score=980_000.0,
                max_units=6,
                max_land_price=980_000.0,
                zoning_district="RM-3-7",
                county="San Diego",
                state="CA",
            ),
        ],
        rejected=[
            ScreeningResult(
                address="1 Nowhere Rd",
                status="rejected",
                reasons=["below min_units"],
            ),
        ],
        errors=[],
        total=2,
        qualified_count=1,
    )

    async def _fake_screen(addresses, buy_box, analyze_fn, **kwargs):
        return batch

    monkeypatch.setattr("plotlot.pipeline.screening.screen_addresses", _fake_screen)
    out = json.loads(
        await _execute_screen_properties(
            {"addresses": ["1233 Hueneme St", "1 Nowhere Rd"], "states": ["CA"], "min_units": 4}
        )
    )
    assert out["status"] == "success"
    assert out["qualified_count"] == 1
    assert out["qualified"][0]["address"] == "1233 Hueneme St"
    assert out["qualified"][0]["max_units"] == 6
    assert out["rejected_count"] == 1
    assert "grounding_note" in out


@pytest.mark.asyncio
async def test_screen_caps_batch_size(monkeypatch):
    seen: dict = {}

    async def _fake_screen(addresses, buy_box, analyze_fn, **kwargs):
        seen["n"] = len(addresses)
        return BatchScreeningResult(total=len(addresses))

    monkeypatch.setattr("plotlot.pipeline.screening.screen_addresses", _fake_screen)
    many = [f"{i} Main St" for i in range(50)]
    await _execute_screen_properties({"addresses": many})
    assert seen["n"] == 20  # capped at _MAX_SCREEN_ADDRESSES


def test_screen_tool_is_registered_and_core():
    names = {t["function"]["name"] for t in CHAT_TOOLS}
    assert "screen_properties" in names
    core_names = {t["function"]["name"] for t in CORE_TOOLS}
    assert "screen_properties" in core_names


def test_new_tools_have_harness_contracts():
    # A missing harness contract makes chat fall into the broken
    # `authorize("gateway.execute")` path and raise KeyError('gateway.execute')
    # the moment the tool is called. Both new tools must be registered.
    assert tool_exists("analyze_property")
    assert tool_exists("screen_properties")


def test_every_chat_tool_has_a_harness_contract():
    # Guard the whole class of bug: any chat tool the model can call MUST have a
    # ToolContract, or the governance gateway 500s the turn. This invariant would
    # have caught the analyze_property/screen_properties gateway.execute error.
    for t in CHAT_TOOLS:
        name = t["function"]["name"]
        assert tool_exists(name), f"chat tool {name!r} has no harness ToolContract"


# ---------------------------------------------------------------------------
# Grounding persists across the conversation (system-prompt injection)
# ---------------------------------------------------------------------------


def test_active_analysis_context_renders_grounded_numbers():
    payload = _format_grounded_analysis(_hueneme_report())
    block = _build_active_analysis_context(payload)
    assert "ACTIVE GROUNDED ANALYSIS" in block
    assert "RM-3-7" in block
    # The follow-up-critical numbers must be present so the model cites them.
    assert "980,000" in block  # residual offer
    assert "420,000" in block  # ADV / exit
    assert "18,000" in block  # impact fees per unit
    # And it must order the model to stop re-deriving / suggesting ingest.
    assert "Do NOT re-derive" in block
    assert "ingesting" in block


def test_active_analysis_context_empty_for_bad_payload():
    assert _build_active_analysis_context({}) == ""
    assert _build_active_analysis_context({"status": "error"}) == ""


@pytest.mark.asyncio
async def test_execute_persists_analysis_for_followup_turns(monkeypatch):
    report = _hueneme_report()

    async def _report(_address):
        return report

    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_deep", _report)
    await _execute_analyze_property("1233 Hueneme St", session_id="s-followup")
    stored = chat_mod._sessions.get_analysis("s-followup")
    assert stored is not None
    assert stored["by_right"]["max_units"] == 6
    # The stored payload is what gets injected on the next turn.
    block = _build_active_analysis_context(stored)
    assert "By-right max units: 6" in block


def test_grounding_policy_blocks_redrive_and_ingest_suggestions():
    policy = GROUNDING_POLICY.lower()
    assert "re-run a" in policy or "re-derive" in policy
    assert "ingest" in policy  # never suggest ingesting (SD already ingested)
    assert "already" in policy and "ingested" in policy
    assert "alternative ordinance" in policy  # never invent a conflicting reading


# ---------------------------------------------------------------------------
# Lot-size provenance gates the "VERIFIED" claim (a count is only as firm as
# the lot area it was built on).
# ---------------------------------------------------------------------------


def test_geometry_lot_makes_unit_count_provisional():
    report = _hueneme_report()  # extraction verifies the ordinance rule
    report.property_record.lot_size_source = "geometry"
    payload = _format_grounded_analysis(report)

    assert payload["lot_size_source"] == "geometry"
    assert "estimate" in payload["lot_size_basis"].lower()
    # Even though the ordinance rule verified, the count is provisional on the lot.
    assert payload["by_right"]["verification"] == "provisional"
    assert payload["by_right"]["offer_is_provisional"] is True
    assert payload["by_right"]["lot_size_confirmed"] is False
    assert any("assessor" in w.lower() for w in payload.get("warnings", []))


def test_assessor_lot_keeps_count_verified():
    report = _hueneme_report()
    report.property_record.lot_size_source = "assessor"
    payload = _format_grounded_analysis(report)

    assert payload["lot_size_source"] == "assessor"
    assert "authoritative" in payload["lot_size_basis"].lower()
    assert payload["by_right"]["verification"] == "verified"
    assert payload["by_right"]["lot_size_confirmed"] is True


def test_unknown_lot_provenance_does_not_downgrade():
    # Providers that don't set provenance (e.g. FL counties) must not regress to
    # provisional — only a KNOWN geometry estimate downgrades trust.
    report = _hueneme_report()
    assert report.property_record.lot_size_source == ""
    payload = _format_grounded_analysis(report)
    assert payload["by_right"]["verification"] == "verified"
    assert payload["by_right"]["lot_size_confirmed"] is False  # not "assessor"


def test_source_answer_flags_provisional_on_geometry_lot():
    from plotlot.api.chat import _build_source_answer

    report = _hueneme_report()
    report.property_record.lot_size_source = "geometry"
    answer = _build_source_answer(_format_grounded_analysis(report))

    assert answer is not None
    assert "PROVISIONAL" in answer
    assert "assessor" in answer.lower()
    # The rule may be verified, but the count is NOT stamped firm-verified.
    assert "Verification status: **VERIFIED**" not in answer


def test_source_answer_verified_on_assessor_lot():
    from plotlot.api.chat import _build_source_answer

    report = _hueneme_report()
    report.property_record.lot_size_source = "assessor"
    answer = _build_source_answer(_format_grounded_analysis(report))

    assert answer is not None
    assert "VERIFIED" in answer
    assert "PROVISIONAL" not in answer


def test_geologic_hazard_surfaced_in_payload():
    from plotlot.core.types import GeologicHazard

    report = _hueneme_report()
    report.site_risk.geologic = GeologicHazard(
        fault_zone="not within an Alquist-Priolo Earthquake Fault Zone",
        landslide_zone="NOT evaluated by CGS for seismic landslide hazards",
        liquefaction_zone="NOT evaluated by CGS for liquefaction hazards",
        in_any_hazard_zone=False,
        evaluated=False,
        flags=[
            "Seismic landslide/liquefaction NOT evaluated by CGS here — geotechnical review needed"
        ],
    )
    payload = _format_grounded_analysis(report)
    geo = payload["site_risk"]["geologic_hazard"]
    assert geo["evaluated"] is False
    assert "CGS" in geo["source"]
    assert any("geotechnical" in f.lower() for f in geo["flags"])


# ---------------------------------------------------------------------------
# Narrator anti-hallucination: deterministic `calculate` tool + MATH/FEE rules
# (regression for the Kevin Woo session — fabricated fees, mental-math errors).
# ---------------------------------------------------------------------------


def test_calculate_tool_registered_and_core():
    names = {t["function"]["name"] for t in CHAT_TOOLS}
    assert "calculate" in names
    from plotlot.api.chat import CORE_TOOLS

    assert "calculate" in {t["function"]["name"] for t in CORE_TOOLS}


def test_calculate_executor_returns_exact_result():
    import json

    from plotlot.api.chat import _execute_calculate

    out = json.loads(_execute_calculate("7 * 750000"))
    assert out["status"] == "success"
    assert out["result"] == 5_250_000  # rendered as int when whole

    gap = json.loads(_execute_calculate("1500000 - 444900"))
    assert gap["result"] == 1_055_100


def test_calculate_executor_rejects_non_arithmetic():
    import json

    from plotlot.api.chat import _execute_calculate

    out = json.loads(_execute_calculate("__import__('os')"))
    assert out["status"] == "error"
    assert "arithmetic" in out["message"].lower()


def test_grounding_policy_has_math_and_fee_rules():
    from plotlot.api.chat import GROUNDING_POLICY

    assert "MATH RULE" in GROUNDING_POLICY
    assert "calculate" in GROUNDING_POLICY
    assert "FEE RULE" in GROUNDING_POLICY
    # The exact phantom categories from the Kevin Woo hallucination are named as banned.
    assert "police fee" in GROUNDING_POLICY.lower()
