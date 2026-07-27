"""Contract tests for the Kleyman step table + HTN decomposition (Slice 2.2).

These pin two spec-derived invariants:

* Spec acceptance #3 (the load-bearing rule): the planner refuses to activate
  step 5 (residual land value) when any ``zoning.*`` claim required by step 2
  is not ``kind=verified_fact``. Density study precedes land valuation,
  enforced by code — ``step_blocked_reasons(RESIDUAL_LAND_VALUE, claims)``
  returns ``("zoning", ...)`` when zoning is missing or only an assumption.

* Spec acceptance #4 (residential vs commercial divergence): step 3 routes to
  the income approach (NOI/cap) for ≥5 units and the comp approach (ARV) for
  ≤4 units — a typed method dispatch, not a prompt hope. Encoded as two HTN
  methods on step 2 (as-built value), selected by ``product.unit_count``.

Spec: specs/agentic-zoning-harness.md, acceptances #3 + #4 + derived required
tests ("planner ordering test: step 5 blocked when zoning.* not verified";
"step-3 branch test: income vs comp approach on unit_count").
"""

from __future__ import annotations

from plotlot.domain import (
    Claim,
    ClaimKind,
    ClaimOrigin,
    KleymanStep,
    StepRequirement,
    all_steps,
    dispatch,
    methods_for,
    requirement_satisfied,
    step_blocked_reasons,
    step_can_activate,
    step_def,
)


# --- the step table is exhaustive + ordered -----------------------------


def test_every_step_has_a_definition():
    assert {sd.step for sd in all_steps()} == set(KleymanStep)
    # declared in HTN order (1..8)
    assert [sd.step for sd in all_steps()] == list(KleymanStep)


def test_step_def_lookup_is_exhaustive():
    for step in KleymanStep:
        assert step_def(step).step is step
        assert step_def(step).produces  # every step produces something
        assert isinstance(step_def(step).produces, tuple)


# --- THE LOAD-BEARING RULE (spec acceptance #3) -------------------------
# step 5 (residual land value) blocks when zoning.* is not verified_fact.


def test_step5_blocked_when_zoning_missing():
    """No zoning claim at all → step 5 blocked on the zoning namespace."""
    claims = (
        Claim(
            field_key="value.stabilized",
            value=1_000_000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
        Claim(
            field_key="cost.hard_per_sqft",
            value=225.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
    )
    blocked = step_blocked_reasons(KleymanStep.RESIDUAL_LAND_VALUE, claims)
    assert "zoning" in blocked
    assert step_can_activate(KleymanStep.RESIDUAL_LAND_VALUE, claims) is False


def test_step5_blocked_when_zoning_only_an_assumption():
    """A zoning claim that exists but is only assumption-grade (not
    verified_fact) still blocks step 5 — the Kleyman boundary is strict.

    (Note: a zoning.* claim with origin != local_authority cannot even be
    constructed; here we use a verified_fact zoning claim demoted in spirit —
    the rule keys off kind, not origin. We satisfy the source boundary by
    using local_authority, then test the kind ladder directly.)
    """
    verified_zoning = Claim(
        field_key="zoning.district",
        value="RM-15",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
    )
    # Simulate a demoted/assumption-grade zoning fact: source_boundary_ok
    # forbids kind=assumption on zoning.* only via origin, so model the
    # "unverified zoning" case as the *absence* of a verified zoning claim —
    # i.e. an assumption-grade product claim but no verified zoning fact.
    claims_without_verified_zoning = (
        Claim(
            field_key="value.stabilized",
            value=1_000_000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
        Claim(
            field_key="cost.hard_per_sqft",
            value=225.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
    )
    blocked = step_blocked_reasons(KleymanStep.RESIDUAL_LAND_VALUE, claims_without_verified_zoning)
    assert "zoning" in blocked
    # and once zoning IS verified, the zoning precondition lifts
    claims_with_verified_zoning = claims_without_verified_zoning + (verified_zoning,)
    blocked2 = step_blocked_reasons(KleymanStep.RESIDUAL_LAND_VALUE, claims_with_verified_zoning)
    assert "zoning" not in blocked2


def test_step5_unblocked_when_all_preconditions_met():
    """Verified zoning + assumption value + assumption cost → step 5 ready."""
    claims = (
        Claim(
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
        ),
        Claim(
            field_key="value.stabilized",
            value=1_000_000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
        Claim(
            field_key="cost.hard_per_sqft",
            value=225.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
        ),
    )
    assert step_blocked_reasons(KleymanStep.RESIDUAL_LAND_VALUE, claims) == ()
    assert step_can_activate(KleymanStep.RESIDUAL_LAND_VALUE, claims) is True


def test_step5_requires_verified_fact_not_assumption_grade_zoning():
    """A requirement pinned to verified_fact is NOT satisfied by an
    assumption-grade claim in the same namespace, even if one exists.

    We can't construct a zoning.assumption claim (source boundary), so we
    test the requirement predicate directly against a stub namespace."""
    assumption_grade = Claim(
        field_key="parcel.lot_area_sqft",  # use parcel namespace to model
        value=10000.0,  # an assumption-grade local fact for the ladder test
        kind=ClaimKind.ASSUMPTION,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
    )
    # parcel.* + assumption does NOT satisfy a verified_fact requirement
    assert (
        requirement_satisfied(
            StepRequirement("parcel", ClaimKind.VERIFIED_FACT), [assumption_grade]
        )
        is False
    )
    # but it DOES satisfy an assumption-minimum requirement
    assert (
        requirement_satisfied(StepRequirement("parcel", ClaimKind.ASSUMPTION), [assumption_grade])
        is True
    )
    # and the off-ladder kinds never satisfy anything
    calc = Claim(
        field_key="value.max_land",
        value=500_000.0,
        kind=ClaimKind.CALCULATION,
        origin=ClaimOrigin.DERIVED_CALC,
    )
    assert requirement_satisfied(StepRequirement("value", ClaimKind.ASSUMPTION), [calc]) is False


def test_step1_has_no_preconditions():
    """Density study is the entry point — nothing blocks it."""
    assert step_blocked_reasons(KleymanStep.DENSITY_STUDY, ()) == ()
    assert step_can_activate(KleymanStep.DENSITY_STUDY, ()) is True


def test_step2_also_requires_verified_zoning():
    """As-built value (step 2) also needs verified zoning — value derives
    from density, which derives from the district."""
    assert "zoning" in step_blocked_reasons(KleymanStep.AS_BUILT_VALUE, ())


# --- RESIDENTIAL vs COMMERCIAL DIVERGENCE (spec acceptance #4) ---------
# step 2 (as-built value) routes income vs comp by unit_count.


def _unit_claim(n: int) -> Claim:
    return Claim(
        field_key="product.unit_count",
        value=float(n),
        kind=ClaimKind.CALCULATION,
        origin=ClaimOrigin.DERIVED_CALC,
    )


def test_step2_has_two_methods_specialized_first():
    ms = methods_for(KleymanStep.AS_BUILT_VALUE)
    assert [m.name for m in ms] == ["step2.income_approach", "step2.comp_approach"]


def test_step2_income_approach_selected_for_multifamily():
    """≥5 units → income approach (NOI/cap), the specialized method wins."""
    d = dispatch(KleymanStep.AS_BUILT_VALUE, (_unit_claim(8),))
    assert d.selected is not None
    assert d.selected.name == "step2.income_approach"
    assert "compute_stabilized_noi" in d.selected.subtasks
    assert "apply_cap_rate" in d.selected.subtasks
    assert d.skipped == ()  # specialized matched first, nothing skipped


def test_step2_comp_approach_selected_for_small_residential():
    """≤4 units → comp approach (ARV × units), the generic fallback."""
    d = dispatch(KleymanStep.AS_BUILT_VALUE, (_unit_claim(2),))
    assert d.selected is not None
    assert d.selected.name == "step2.comp_approach"
    assert "fetch_comps" in d.selected.subtasks
    assert d.skipped == ("step2.income_approach",)  # specialized didn't match


def test_step2_boundary_unit_count_five_takes_income():
    """Exactly 5 units is multifamily → income approach."""
    d = dispatch(KleymanStep.AS_BUILT_VALUE, (_unit_claim(5),))
    assert d.selected.name == "step2.income_approach"


def test_step2_boundary_unit_count_four_takes_comp():
    """Exactly 4 units is small residential → comp approach."""
    d = dispatch(KleymanStep.AS_BUILT_VALUE, (_unit_claim(4),))
    assert d.selected.name == "step2.comp_approach"


def test_step2_dispatch_is_pure():
    """Same claims → same selection, every call (no hidden state)."""
    claims = (_unit_claim(3),)
    assert (
        dispatch(KleymanStep.AS_BUILT_VALUE, claims).selected
        is dispatch(KleymanStep.AS_BUILT_VALUE, claims).selected
    )


# --- every step has at least one applicable method -----------------------


def test_every_step_has_a_dispatchable_method():
    """No step should be left without a decomposition — a step with no
    method is a misconfiguration the planner would hit as a dead end."""
    for step in KleymanStep:
        assert dispatch(step, ()).selected is not None, f"{step!r} has no method"
