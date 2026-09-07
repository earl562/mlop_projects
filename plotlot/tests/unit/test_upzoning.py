"""Tests for the upzoning / subdivision value-creation engine.

The engine prices the developer's core play: the equity created by changing a
parcel's legal yield (subdivide / rezone) *before* building. Tests lock in the
deterministic subdivision yield, the instant-equity math (validated against the
Daniel Clayman case study the feature was modeled on), the exit options, and the
honesty guards (no per-lot value → equity left uncomputed, not guessed).
"""

from __future__ import annotations

from plotlot.pipeline.upzoning import analyze_upzoning, subdivision_lot_yield

# Clayman case study: half-acre parcel, 5 lots by-right → 12 via special-use
# permit, ~$90k/lot, $628k purchase + ~$29k entitlement soft costs = $657k basis.
HALF_ACRE_SQFT = 21_780.0


# ---------------------------------------------------------------------------
# subdivision_lot_yield
# ---------------------------------------------------------------------------


def test_subdivision_yield_area_based():
    lots, formula = subdivision_lot_yield(HALF_ACRE_SQFT, 4_000.0)
    assert lots == 5  # floor(21780 / 4000) = 5
    assert "21,780" in formula and "5 conforming lot(s)" in formula


def test_subdivision_yield_frontage_can_bind():
    # Area allows 5, but only 200 ft of frontage at 50 ft/lot allows 4 → 4 governs.
    lots, formula = subdivision_lot_yield(
        HALF_ACRE_SQFT, 4_000.0, min_lot_width_ft=50.0, lot_frontage_ft=200.0
    )
    assert lots == 4
    assert "frontage" in formula


def test_subdivision_yield_insufficient_data():
    assert subdivision_lot_yield(0, 4_000.0)[0] == 0
    assert subdivision_lot_yield(HALF_ACRE_SQFT, 0)[0] == 0


# ---------------------------------------------------------------------------
# analyze_upzoning — the instant-equity headline
# ---------------------------------------------------------------------------


def test_case_study_instant_equity():
    """Reproduce the case study: 5 → 12 lots at $90k creates $423k instant equity."""
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=90_000.0,
        purchase_price=628_000.0,
        entitlement_soft_costs=29_000.0,
        baseline_yield=5,
        upzoned_yield=12,
        value_source="override",
    )
    assert a.all_in_basis == 657_000.0
    assert a.upzoned is not None and a.upzoned.gross_value == 1_080_000.0
    assert a.equity_created == 423_000.0  # 1,080,000 − 657,000
    assert a.value_uplift == 630_000.0  # (12 − 5) × 90,000
    assert round(a.cost_per_yield) == 54_750  # 657,000 / 12
    assert a.value_source == "override"


def test_partial_sale_for_free_land_matches_case_study():
    """The 'free land' exit: sell 8 lots to recover the $657k basis, keep 4 free."""
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=90_000.0,
        purchase_price=628_000.0,
        entitlement_soft_costs=29_000.0,
        baseline_yield=5,
        upzoned_yield=12,
    )
    free_land = next((o for o in a.exit_options if "for free" in o), None)
    assert free_land is not None
    # ceil(657,000 / 90,000) = 8 lots to recover basis; 12 − 8 = 4 kept free.
    assert "Sell 8" in free_land
    assert "keep the remaining 4 for free" in free_land


def test_yields_resolved_from_min_lot_area():
    """When yields aren't given directly, they're derived from min lot area."""
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=90_000.0,
        purchase_price=657_000.0,
        baseline_min_lot_area_sqft=4_000.0,  # → 5 lots
        upzoned_min_lot_area_sqft=1_815.0,  # → 12 lots
    )
    assert a.baseline is not None and a.baseline.yield_count == 5
    assert a.upzoned is not None and a.upzoned.yield_count == 12


def test_missing_per_lot_value_does_not_fabricate_equity():
    """No per-lot value → yields returned, equity left at zero with a warning."""
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=None,
        purchase_price=628_000.0,
        baseline_yield=5,
        upzoned_yield=12,
    )
    assert a.value_source == "missing"
    assert a.equity_created == 0.0
    assert a.exit_options == []
    assert any("per-lot value" in w for w in a.warnings)
    # Yields are still useful even without a value.
    assert a.upzoned is not None and a.upzoned.yield_count == 12


def test_non_comp_value_source_flagged_as_estimate():
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=90_000.0,
        baseline_yield=5,
        upzoned_yield=12,
        value_source="regional_estimate",
    )
    assert any("estimate" in n for n in a.notes)


def test_missing_upzoned_target_warns():
    a = analyze_upzoning(
        lot_sqft=HALF_ACRE_SQFT,
        value_per_lot=90_000.0,
        baseline_yield=5,
    )
    assert a.upzoned is None
    assert any("upzoned target" in w for w in a.warnings)


# ---------------------------------------------------------------------------
# Chat tool wiring (reachable, contracted — not orphaned)
# ---------------------------------------------------------------------------


def test_upzoning_tool_registered_and_core():
    from plotlot.api.chat import CHAT_TOOLS, CORE_TOOLS
    from plotlot.harness.tool_registry import tool_exists

    assert "analyze_upzoning" in {t["function"]["name"] for t in CHAT_TOOLS}
    assert "analyze_upzoning" in {t["function"]["name"] for t in CORE_TOOLS}
    assert tool_exists("analyze_upzoning")  # has a harness ToolContract


def test_chat_executor_returns_equity_json():
    import json

    from plotlot.api.chat import _execute_analyze_upzoning

    out = json.loads(
        _execute_analyze_upzoning(
            {
                "lot_sqft": HALF_ACRE_SQFT,
                "value_per_lot": 90_000,
                "purchase_price": 628_000,
                "entitlement_soft_costs": 29_000,
                "baseline_yield": 5,
                "upzoned_yield": 12,
            }
        )
    )
    assert out["status"] == "success"
    assert out["equity_created"] == 423_000
    assert out["cost_per_yield"] == 54_750
    assert out["upzoned"]["yield_count"] == 12
    assert any("for free" in o for o in out["exit_options"])


def test_chat_executor_requires_lot_sqft():
    import json

    from plotlot.api.chat import _execute_analyze_upzoning

    out = json.loads(_execute_analyze_upzoning({"value_per_lot": 90_000}))
    assert out["status"] == "error"
