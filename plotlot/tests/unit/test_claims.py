"""Contract tests for the typed-claim spine (Slice 2.1).

These pin the source-boundary invariant: the Rehab Valuator corpus is
authoritative for underwriting concepts, NOT for local facts. A zoning.*
claim with origin=rehabvaluator_concept, or a cost.* claim with
kind=verified_fact, is a validation FAILURE (raises), not a warning.

Spec: specs/agentic-zoning-harness.md, invariant #2 (source boundary) +
derived required test: "Boundary invariant tests: zoning.*+non-local-authority
raises; cost.*+verified_fact raises."
"""

from __future__ import annotations

import pytest

from plotlot.domain import (
    Claim,
    ClaimKind,
    ClaimOrigin,
    SourceBoundaryViolation,
    source_boundary_ok,
)

from dataclasses import dataclass, field


# --- construction: the happy path ---------------------------------------


def test_verified_zoning_claim_from_local_authority_constructs():
    c = Claim(
        field_key="zoning.district",
        value="RM-15",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        evidence_ids=("sec:fort-lauderdale/47-5.60",),
        source_url="https://www.municode.com/...",
    )
    assert c.field_key == "zoning.district"
    assert c.namespace == "zoning"
    assert c.kind is ClaimKind.VERIFIED_FACT
    assert source_boundary_ok(c) is True


def test_cost_assumption_claim_constructs():
    c = Claim(
        field_key="cost.hard_per_sqft",
        value=225.0,
        kind=ClaimKind.ASSUMPTION,
        origin=ClaimOrigin.USER_PROVIDED,
        confidence=0.4,
    )
    assert c.namespace == "cost"
    assert source_boundary_ok(c) is True


def test_hypothesis_requires_next_verification_step():
    # without next_verification_step → raises (boundary)
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key="entitlement.upzone",
            value=True,
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )
    # with one → constructs
    c = Claim(
        field_key="entitlement.upzone",
        value=True,
        kind=ClaimKind.HYPOTHESIS,
        origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        next_verification_step="Confirm RM-15→RM-25 rezoning eligibility with planner",
    )
    assert source_boundary_ok(c) is True


def test_contradiction_requires_rival_ids():
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key="zoning.setback_front_ft",
            value=20.0,
            kind=ClaimKind.CONTRADICTION,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            evidence_ids=("a",),
        )
    c = Claim(
        field_key="zoning.setback_front_ft",
        value=20.0,
        kind=ClaimKind.CONTRADICTION,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        evidence_ids=("a",),
        metadata={"contradicts": ("a", "b")},
    )
    assert source_boundary_ok(c) is True


# --- the source-boundary invariant (the load-bearing tests) -------------


@pytest.mark.parametrize(
    "origin",
    [
        ClaimOrigin.REHABVALUATOR_CONCEPT,
        ClaimOrigin.USER_PROVIDED,
        ClaimOrigin.DERIVED_CALC,
        ClaimOrigin.UNKNOWN,
    ],
)
def test_zoning_claim_with_non_local_authority_origin_raises(origin):
    """A zoning.* claim MUST originate from a local authority.

    The Rehab Valuator corpus is not a zoning oracle. A concept from the
    corpus flagged as origin=rehabvaluator_concept cannot ground zoning.district.
    """
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key="zoning.district",
            value="RM-15",
            kind=ClaimKind.VERIFIED_FACT,
            origin=origin,
        )


def test_parcel_claim_with_non_local_authority_origin_raises():
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key="parcel.lot_area_sqft",
            value=10000.0,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.REHABVALUATOR_CONCEPT,
        )


@pytest.mark.parametrize(
    "field_key",
    [
        "cost.hard_per_sqft",
        "cost.soft_per_sqft",
        "cap_rate.market",
        "financing.construction_ltc",
        "rent.market_per_unit",
    ],
)
def test_assumption_namespace_claim_with_verified_fact_kind_raises(field_key):
    """Costs/cap rates/financing/rent are NEVER verified_fact — they are
    market-derived or user-supplied assumptions."""
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key=field_key,
            value=225.0,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
        )


def test_unknown_origin_confidence_capped_at_half():
    """Scraped comps (origin=unknown) are amber, never authoritative:
    confidence is capped at 0.5."""
    with pytest.raises(SourceBoundaryViolation):
        Claim(
            field_key="comp.sale_price",
            value=2_000_000.0,
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.UNKNOWN,
            confidence=0.7,
        )
    # at the cap → ok
    c = Claim(
        field_key="comp.sale_price",
        value=2_000_000.0,
        kind=ClaimKind.ASSUMPTION,
        origin=ClaimOrigin.UNKNOWN,
        confidence=0.5,
        source_url="https://example.com/listing/123",
    )
    assert source_boundary_ok(c) is True


# --- predicate form (for downstream guardrails / report validator) -------


def test_source_boundary_ok_predicate_matches_constructor():
    """The predicate mirrors the constructor; downstream rules can assert it
    over serialized/loaded claim rows (which may have bypassed construction).
    We feed it a lightweight stub carrying the same attributes a deserialized
    Claim row would, including boundary-breaking ones the constructor refuses."""
    ok = Claim(
        field_key="zoning.district",
        value="RM-15",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
    )
    assert source_boundary_ok(ok) is True

    # A boundary-breaking row the constructor would have refused — simulate a
    # deserialized row that bypassed __post_init__ (e.g. loaded from a ClaimLog
    # table written by an older, less-strict version).
    @dataclass
    class _Stub:
        field_key: str
        value: object
        kind: ClaimKind
        origin: ClaimOrigin
        confidence: float | None = None
        evidence_ids: tuple[str, ...] = ()
        source_url: str = ""
        next_verification_step: str = ""
        extracted_at: str = ""
        metadata: dict[str, object] = field(default_factory=dict)

    bad = _Stub(
        field_key="zoning.district",
        value="RM-15",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.REHABVALUATOR_CONCEPT,  # corpus cannot ground zoning.*
    )
    assert source_boundary_ok(bad) is False


def test_claim_is_frozen_and_hashable_by_identity():
    """Claims are immutable (frozen=True) — guardrails/report layers must not
    mutate a claim in place; they emit new claims instead."""
    c = Claim(
        field_key="zoning.far",
        value=2.5,
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
    )
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclass detail
        c.value = 3.0  # type: ignore[misc]


def test_namespace_extraction():
    """Namespaces drive the boundary rules; extraction is the first dot segment."""
    assert (
        Claim(
            field_key="zoning.setback_front_ft",
            value=20.0,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
        ).namespace
        == "zoning"
    )
    # bare key (no dot) → its own namespace
    assert _bare_namespace("cap_rate") == "cap_rate"


def _bare_namespace(key: str) -> str:
    c = Claim(
        field_key=key,
        value=0.05,
        kind=ClaimKind.ASSUMPTION,
        origin=ClaimOrigin.USER_PROVIDED,
    )
    return c.namespace
