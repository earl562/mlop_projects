"""Contract tests for the claim-log guardrails (Slice 2.3).

These pin the 5 Kleyman guardrails from the harness spec (acceptance #7:
"report as claim projection" — fails on missing evidence_ids / blurred
boundaries / hidden contradictions). The guardrails run over a ``Claim[]``
(loaded from storage / aggregated across runs), which is why they must
re-validate even what the Claim constructor already enforces: a claim-log
row can bypass construction.

Rules 1–3 overlap with the per-claim constructor invariants in
:mod:`plotlot.domain.claims`. To test the *guardrail* layer firing on a
log row that *would* have failed construction, we use a lightweight stub
dataclass carrying the same attrs as ``Claim`` (the established pattern —
see the Codebase Patterns note in progress.txt: a frozen ``Claim`` cannot
be mutated, so predicate-form rules are exercised over a matching stub).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plotlot.domain import (
    ASSUMPTION_NAMESPACES,
    LOCAL_AUTHORITY_NAMESPACES,
    Claim,
    ClaimKind,
    ClaimOrigin,
    GuardrailRule,
    evaluate_guardrails,
    human_review_violations,
    integrity_violations,
    is_material,
    requires_human_review,
    source_boundary_ok,
)


# ---------------------------------------------------------------------------
# Stub claim — mirrors Claim's read surface for the guardrails, but does NOT
# run __post_init__. Used to model boundary-violating rows that bypassed
# construction (rules 1–3 can't be built as real Claims).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StubClaim:
    field_key: str
    value: Any = None
    kind: ClaimKind = ClaimKind.ASSUMPTION
    origin: ClaimOrigin = ClaimOrigin.UNKNOWN
    confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()
    source_url: str = ""
    next_verification_step: str = ""
    extracted_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def namespace(self) -> str:
        if not self.field_key:
            return ""
        return self.field_key.split(".", 1)[0]


# --- helpers to build valid real Claims (happy-path fixtures) -------------


def _verified_zoning(field_key: str = "zoning.district", value: Any = "RM-15") -> Claim:
    return Claim(
        field_key=field_key,
        value=value,
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        evidence_ids=("sec:fl/47-5.60",),
        source_url="https://www.municode.com/...",
    )


def _cost_assumption() -> Claim:
    return Claim(
        field_key="cost.hard_per_sqft",
        value=225.0,
        kind=ClaimKind.ASSUMPTION,
        origin=ClaimOrigin.USER_PROVIDED,
        confidence=0.4,
    )


def _entitlement_hypothesis() -> Claim:
    return Claim(
        field_key="entitlement.upzone",
        value=True,
        kind=ClaimKind.HYPOTHESIS,
        origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        next_verification_step="Confirm RM-15→RM-25 rezoning eligibility with planner",
    )


def _contradiction() -> Claim:
    return Claim(
        field_key="zoning.setback_front_ft",
        value=20.0,
        kind=ClaimKind.CONTRADICTION,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        evidence_ids=("sec:a", "sec:b"),
        metadata={"contradicts": ("sec:a", "sec:b")},
    )


# ===========================================================================
# Rule 1 — LOCAL_AUTHORITY_ORIGIN
# ===========================================================================


class TestRule1LocalAuthorityOrigin:
    def test_clean_log_no_violations(self):
        claims = [_verified_zoning()]
        v = evaluate_guardrails(claims)
        assert all(x.rule is not GuardrailRule.LOCAL_AUTHORITY_ORIGIN for x in v)

    def test_zoning_from_corpus_flagged(self):
        # A zoning.district claim sourced from the Rehab Valuator corpus —
        # the boundary blurred. (Bypasses construction via stub.)
        bad = StubClaim(
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
            evidence_ids=("corpus:rv",),
        )
        v = evaluate_guardrails([bad])
        r1 = [x for x in v if x.rule is GuardrailRule.LOCAL_AUTHORITY_ORIGIN]
        assert len(r1) == 1
        assert r1[0].field_key == "zoning.district"
        assert "local_authority" in r1[0].message or "local-authority" in r1[0].message
        assert not r1[0].requires_human_review

    def test_parcel_from_unknown_origin_flagged(self):
        # Scraped parcel fact — origin=unknown cannot ground a parcel.* claim.
        bad = StubClaim(
            field_key="parcel.lot_area_sqft",
            value=7000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.UNKNOWN,
            confidence=0.3,
        )
        v = evaluate_guardrails([bad])
        r1 = [x for x in v if x.rule is GuardrailRule.LOCAL_AUTHORITY_ORIGIN]
        assert len(r1) == 1
        assert r1[0].field_key == "parcel.lot_area_sqft"

    def test_all_local_authority_namespaces_covered(self):
        # The rule must fire for EVERY namespace in LOCAL_AUTHORITY_NAMESPACES.
        for ns in LOCAL_AUTHORITY_NAMESPACES:
            bad = StubClaim(
                field_key=f"{ns}.x",
                value=1,
                kind=ClaimKind.ASSUMPTION,
                origin=ClaimOrigin.USER_PROVIDED,
            )
            v = evaluate_guardrails([bad])
            assert any(x.rule is GuardrailRule.LOCAL_AUTHORITY_ORIGIN for x in v), ns

    def test_non_local_authority_namespace_not_flagged_by_rule1(self):
        # A cost.* claim with non-local-authority origin is fine for rule 1
        # (rule 2 governs cost.*). Rule 1 must not over-fire.
        c = _cost_assumption()
        v = evaluate_guardrails([c])
        assert all(x.rule is not GuardrailRule.LOCAL_AUTHORITY_ORIGIN for x in v)


# ===========================================================================
# Rule 2 — ASSUMPTION_NAMESPACE
# ===========================================================================


class TestRule2AssumptionNamespace:
    def test_clean_cost_assumption_no_rule2_violation(self):
        v = evaluate_guardrails([_cost_assumption()])
        assert all(x.rule is not GuardrailRule.ASSUMPTION_NAMESPACE for x in v)

    def test_cost_as_verified_fact_flagged(self):
        # cost.hard_per_sqft presented as verified_fact — forbidden.
        bad = StubClaim(
            field_key="cost.hard_per_sqft",
            value=225.0,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            evidence_ids=("e1",),
        )
        v = evaluate_guardrails([bad])
        r2 = [x for x in v if x.rule is GuardrailRule.ASSUMPTION_NAMESPACE]
        assert len(r2) == 1
        assert "verified_fact" in r2[0].message or "assumption" in r2[0].message
        assert not r2[0].requires_human_review

    def test_all_assumption_namespaces_covered(self):
        for ns in ASSUMPTION_NAMESPACES:
            bad = StubClaim(
                field_key=f"{ns}.x",
                value=1.0,
                kind=ClaimKind.VERIFIED_FACT,
                origin=ClaimOrigin.LOCAL_AUTHORITY,
                evidence_ids=("e",),
            )
            v = evaluate_guardrails([bad])
            assert any(x.rule is GuardrailRule.ASSUMPTION_NAMESPACE for x in v), ns

    def test_cap_rate_assumption_not_flagged(self):
        c = Claim(
            field_key="cap_rate.market",
            value=0.06,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.USER_PROVIDED,
            confidence=0.4,
        )
        v = evaluate_guardrails([c])
        assert all(x.rule is not GuardrailRule.ASSUMPTION_NAMESPACE for x in v)


# ===========================================================================
# Rule 3 — HYPOTHESIS_VERIFICATION
# ===========================================================================


class TestRule3HypothesisVerification:
    def test_entitlement_hypothesis_with_step_is_clean(self):
        v = evaluate_guardrails([_entitlement_hypothesis()])
        assert all(x.rule is not GuardrailRule.HYPOTHESIS_VERIFICATION for x in v)

    def test_hypothesis_without_step_flagged(self):
        # An entitlement upside claim with no next_verification_step —
        # presented as guaranteed. (Bypasses construction via stub.)
        bad = StubClaim(
            field_key="entitlement.upzone",
            value=True,
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
        v = evaluate_guardrails([bad])
        r3 = [x for x in v if x.rule is GuardrailRule.HYPOTHESIS_VERIFICATION]
        assert len(r3) == 1
        assert "next_verification_step" in r3[0].message
        assert not r3[0].requires_human_review

    def test_lot_split_hypothesis_without_step_flagged(self):
        # Opportunity-skill hypothesis (lot_split_feasibility) — same rule.
        bad = StubClaim(
            field_key="opportunity.lot_split",
            value=True,
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
        v = evaluate_guardrails([bad])
        assert any(x.rule is GuardrailRule.HYPOTHESIS_VERIFICATION for x in v)


# ===========================================================================
# Rule 4 — MATERIAL_EVIDENCE
# ===========================================================================


class TestRule4MaterialEvidence:
    def test_is_material_verified_fact(self):
        assert is_material(_verified_zoning()) is True

    def test_is_material_output_namespace(self):
        rec = Claim(
            field_key="recommendation.go_no_go",
            value="go",
            kind=ClaimKind.CALCULATION,
            origin=ClaimOrigin.DERIVED_CALC,
            evidence_ids=("calc:1",),
        )
        assert is_material(rec) is True

    def test_is_material_not_for_pure_assumption(self):
        # A user-supplied cost assumption is NOT material — it's amber-rendered
        # and provenance-tracked via source_url, not evidence rows.
        assert is_material(_cost_assumption()) is False

    def test_verified_fact_without_evidence_flagged(self):
        # A zoning verified_fact with no evidence_ids — unsupported foundation.
        bad = StubClaim(
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            evidence_ids=(),
        )
        v = evaluate_guardrails([bad])
        r4 = [x for x in v if x.rule is GuardrailRule.MATERIAL_EVIDENCE]
        assert len(r4) == 1
        assert "evidence_ids" in r4[0].message
        assert not r4[0].requires_human_review

    def test_recommendation_without_evidence_flagged(self):
        bad = StubClaim(
            field_key="recommendation.go_no_go",
            value="go",
            kind=ClaimKind.CALCULATION,
            origin=ClaimOrigin.DERIVED_CALC,
            evidence_ids=(),
        )
        v = evaluate_guardrails([bad])
        assert any(x.rule is GuardrailRule.MATERIAL_EVIDENCE for x in v)

    def test_value_claim_with_evidence_is_clean(self):
        c = Claim(
            field_key="value.stabilized",
            value=2_000_000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            evidence_ids=("comp:1", "comp:2"),
        )
        v = evaluate_guardrails([c])
        assert all(x.rule is not GuardrailRule.MATERIAL_EVIDENCE for x in v)

    def test_cost_assumption_without_evidence_not_flagged(self):
        # Pure assumptions are exempt — no evidence_ids required.
        c = _cost_assumption()
        assert c.evidence_ids == ()
        v = evaluate_guardrails([c])
        assert all(x.rule is not GuardrailRule.MATERIAL_EVIDENCE for x in v)


# ===========================================================================
# Rule 5 — CONTRADICTION_REVIEW
# ===========================================================================


class TestRule5ContradictionReview:
    def test_contradiction_surfaces_for_human_review(self):
        v = evaluate_guardrails([_contradiction()])
        r5 = [x for x in v if x.rule is GuardrailRule.CONTRADICTION_REVIEW]
        assert len(r5) == 1
        assert r5[0].requires_human_review is True
        assert "adjudicate" in r5[0].message or "human" in r5[0].message

    def test_requires_human_review_helper(self):
        assert requires_human_review([_contradiction()]) is True
        assert requires_human_review([_verified_zoning()]) is False
        assert requires_human_review([]) is False

    def test_contradiction_is_not_an_integrity_failure(self):
        # A contradiction is an escalation, NOT a broken log — the log may be
        # perfectly consistent; it just needs adjudication.
        v = evaluate_guardrails([_contradiction()])
        assert integrity_violations(v) == ()
        assert len(human_review_violations(v)) == 1


# ===========================================================================
# evaluate_guardrails — composition + determinism
# ===========================================================================


class TestEvaluateGuardrails:
    def test_clean_log_returns_empty(self):
        claims = [_verified_zoning(), _cost_assumption(), _entitlement_hypothesis()]
        assert evaluate_guardrails(claims) == ()

    def test_multiple_violations_all_returned(self):
        # Three independent rule failures in one log.
        bad_zoning = StubClaim(  # rule 1
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
        bad_cost = StubClaim(  # rule 2
            field_key="cost.hard_per_sqft",
            value=225.0,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            evidence_ids=("e",),
        )
        bad_hyp = StubClaim(  # rule 3
            field_key="entitlement.upzone",
            value=True,
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
        v = evaluate_guardrails([bad_zoning, bad_cost, bad_hyp])
        rules = {x.rule for x in v}
        assert GuardrailRule.LOCAL_AUTHORITY_ORIGIN in rules
        assert GuardrailRule.ASSUMPTION_NAMESPACE in rules
        assert GuardrailRule.HYPOTHESIS_VERIFICATION in rules

    def test_deterministic(self):
        bad = StubClaim(
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
        runs = [evaluate_guardrails([bad]) for _ in range(20)]
        assert all(r == runs[0] for r in runs)

    def test_violation_order_stable(self):
        # Rules applied in declaration order: 1, 2, 3, 4, 5.
        bads = [
            StubClaim(
                field_key="zoning.district",
                value="x",
                kind=ClaimKind.VERIFIED_FACT,
                origin=ClaimOrigin.UNKNOWN,
            ),  # rule1 (+rule4 no ev)
            StubClaim(
                field_key="cost.x",
                value=1.0,
                kind=ClaimKind.VERIFIED_FACT,
                origin=ClaimOrigin.LOCAL_AUTHORITY,
                evidence_ids=("e",),
            ),  # rule2
            StubClaim(
                field_key="entitlement.up",
                value=True,
                kind=ClaimKind.HYPOTHESIS,
                origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
            ),  # rule3
        ]
        rules = [x.rule for x in evaluate_guardrails(bads)]
        # rule 1 (local authority) before rule 2 (assumption) before rule 3
        i1 = rules.index(GuardrailRule.LOCAL_AUTHORITY_ORIGIN)
        i2 = rules.index(GuardrailRule.ASSUMPTION_NAMESPACE)
        i3 = rules.index(GuardrailRule.HYPOTHESIS_VERIFICATION)
        assert i1 < i2 < i3

    def test_empty_log(self):
        assert evaluate_guardrails([]) == ()


# ===========================================================================
# Consistency with claims.py — the boundary the guardrails re-check is the
# SAME one the Claim constructor enforces. A claim that passes construction
# also passes the guardrails (no false positives on valid claims).
# ===========================================================================


class TestConsistencyWithConstructor:
    def test_constructible_claim_passes_boundary_rules(self):
        for c in [_verified_zoning(), _cost_assumption(), _entitlement_hypothesis()]:
            assert source_boundary_ok(c) is True
            v = evaluate_guardrails([c])
            # rules 1-3 must not fire on a constructible claim
            for rule in (
                GuardrailRule.LOCAL_AUTHORITY_ORIGIN,
                GuardrailRule.ASSUMPTION_NAMESPACE,
                GuardrailRule.HYPOTHESIS_VERIFICATION,
            ):
                assert all(x.rule is not rule for x in v), (c.field_key, rule)
