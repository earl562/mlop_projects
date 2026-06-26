"""Claim-log guardrails — the report validator's foundation.

These are the 5 Kleyman guardrails from the harness spec, expressed as pure
functions over a ``Claim[]`` (a claim log). They are the set-level analog of
the per-claim invariants in :mod:`plotlot.domain.claims`: the Claim
constructor enforces the source boundary on a *single* freshly-built claim,
but a claim log is loaded from storage / aggregated across agent runs / fed
by tools that may bypass construction. The guardrails re-validate the whole
set so the report (Slice 12.1) never renders a broken log as authoritative.

The 5 rules (spec §invariants + acceptance #7 "report as claim projection"):

1. **LOCAL_AUTHORITY_ORIGIN** — ``zoning.*`` / ``parcel.*`` claims must be
   ``origin=local_authority``. A zoning fact from the Rehab Valuator corpus
   (or scraped) is a blurred boundary — the corpus is not a zoning oracle.
2. **ASSUMPTION_NAMESPACE** — ``cost.*`` / ``cap_rate`` / ``financing.*`` /
   ``rent.*`` claims must be assumption-grade, never ``kind=verified_fact``.
   Market numbers are not grounded in a local authority the way an ordinance is.
3. **HYPOTHESIS_VERIFICATION** — ``kind=hypothesis`` claims (entitlement upside,
   lot-split feasibility, etc.) must carry a ``next_verification_step``.
   Entitlement upside is never presented as guaranteed.
4. **MATERIAL_EVIDENCE** — material claims (those that drive the go/no-go)
   must carry at least one ``evidence_id``. A decision-grade claim with no
   evidence is an unsupported assertion.
5. **CONTRADICTION_REVIEW** — ``kind=contradiction`` claims surface for human
   review. The report must never hide a contradiction behind a confident number.

Rules 1–4 are data-integrity failures (the log is internally inconsistent).
Rule 5 is an escalation: it does not mean the log is broken, only that a human
must adjudicate before the report commits to a number. ``requires_human_review``
on the violation distinguishes the two.

Transport-free: pure data + pure functions. No imports from harness/api/tools.
Slice 2.3 — guardrails over Claim[]. Slice 12.2 wires these into the report
validator; Slice 5.3 may surface them in the agent loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from plotlot.domain.claims import (
    ASSUMPTION_NAMESPACES,
    LOCAL_AUTHORITY_NAMESPACES,
    Claim,
    ClaimKind,
    ClaimOrigin,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class GuardrailRule(str, Enum):
    """The 5 Kleyman guardrails. Identifies which rule a violation breaks."""

    LOCAL_AUTHORITY_ORIGIN = "local_authority_origin"
    ASSUMPTION_NAMESPACE = "assumption_namespace"
    HYPOTHESIS_VERIFICATION = "hypothesis_verification"
    MATERIAL_EVIDENCE = "material_evidence"
    CONTRADICTION_REVIEW = "contradiction_review"


# Field-key namespaces whose claims drive the go/no-go recommendation and so
# are "material" — a material claim with no evidence_ids is an unsupported
# assertion the report must not lean on. A claim is material if EITHER:
#   - it is the load-bearing foundation (kind=verified_fact), OR
#   - it is a decision output (recommendation/metrics/value namespace).
# Pure assumptions (a user-supplied cost, a market cap rate) are NOT material
# here: they're already rendered amber and confidence-capped by the boundary,
# and their provenance is ``source_url``/``origin`` rather than evidence rows.
_MATERIAL_OUTPUT_NAMESPACES: frozenset[str] = frozenset(
    {
        "recommendation",  # recommendation.go_no_go
        "metrics",  # metrics.coc, metrics.dscr, metrics.sweat_equity
        "value",  # value.stabilized, value.max_land, value.gdv
    }
)


@dataclass(frozen=True, slots=True)
class GuardrailViolation:
    """One broken guardrail, located at a claim.

    Attributes:
        rule: which :class:`GuardrailRule` fired.
        field_key: the offending claim's field_key (locates the claim).
        message: human-readable explanation (for traces / the report's
            "needs attention" panel). Deterministic — same claim → same message.
        requires_human_review: ``True`` only for rule 5 (contradictions). These
            are escalations, not integrity failures: the log may be perfectly
            consistent, but a human must adjudicate before committing to a number.
    """

    rule: GuardrailRule
    field_key: str
    message: str
    requires_human_review: bool = False


def is_material(claim: Claim) -> bool:
    """Is ``claim`` load-bearing for the go/no-go decision?

    Material claims must carry ``evidence_ids`` (rule 4). A claim is material
    if it is a verified foundation fact OR a decision-output claim
    (recommendation / metrics / value). Assumptions are excluded — they're
    already amber-rendered and provenance-tracked via ``source_url``.
    """
    if claim.kind == ClaimKind.VERIFIED_FACT:
        return True
    return claim.namespace in _MATERIAL_OUTPUT_NAMESPACES


# ---------------------------------------------------------------------------
# Individual rules — each pure, returns the violations it finds in ``claims``.
# Split out so the report validator (Slice 12.2) can ask "is THIS rule clean?"
# without evaluating the whole set.
# ---------------------------------------------------------------------------


def check_local_authority_origin(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Rule 1: zoning.*/parcel.* must originate from a local authority.

    A zoning/parcel claim with ``origin != local_authority`` (corpus concept,
    scraped, user-stated) is a blurred source boundary — it must not be
    presented as a grounded local fact.
    """
    violations: list[GuardrailViolation] = []
    for c in claims:
        if c.namespace in LOCAL_AUTHORITY_NAMESPACES and c.origin != ClaimOrigin.LOCAL_AUTHORITY:
            violations.append(
                GuardrailViolation(
                    rule=GuardrailRule.LOCAL_AUTHORITY_ORIGIN,
                    field_key=c.field_key,
                    message=(
                        f"{c.field_key!r} is a local-authority namespace ({c.namespace!r}) "
                        f"but origin={c.origin.value!r} — zoning/parcel facts must come "
                        "from a local authority (.gov ordinance / county record), not the "
                        "Rehab Valuator corpus, scraping, or unverified user input."
                    ),
                )
            )
    return tuple(violations)


def check_assumption_namespace(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Rule 2: cost.*/cap_rate/financing.*/rent.* must be assumption-grade.

    A market-number claim presented as ``kind=verified_fact`` claims a local
    authority grounds it — but costs/cap rates/financing terms are always
    assumptions (market-derived or user-supplied), never verified facts.
    """
    violations: list[GuardrailViolation] = []
    for c in claims:
        if c.namespace in ASSUMPTION_NAMESPACES and c.kind == ClaimKind.VERIFIED_FACT:
            violations.append(
                GuardrailViolation(
                    rule=GuardrailRule.ASSUMPTION_NAMESPACE,
                    field_key=c.field_key,
                    message=(
                        f"{c.field_key!r} is in an assumption namespace ({c.namespace!r}) "
                        "but kind=verified_fact — costs, cap rates, financing terms, and "
                        "rents are always assumptions, never verified facts."
                    ),
                )
            )
    return tuple(violations)


def check_hypothesis_verification(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Rule 3: hypotheses must declare a next_verification_step.

    Entitlement upside, lot-split feasibility, and other speculative claims
    must state how they'd be promoted or demoted — they are never presented
    as guaranteed. (This re-checks what the Claim constructor enforces, for
    claim-log rows that bypassed construction.)
    """
    violations: list[GuardrailViolation] = []
    for c in claims:
        if c.kind == ClaimKind.HYPOTHESIS and not c.next_verification_step:
            violations.append(
                GuardrailViolation(
                    rule=GuardrailRule.HYPOTHESIS_VERIFICATION,
                    field_key=c.field_key,
                    message=(
                        f"{c.field_key!r} is kind=hypothesis but has no "
                        "next_verification_step — entitlement upside must state how "
                        "it would be promoted or demoted before the report renders it."
                    ),
                )
            )
    return tuple(violations)


def check_material_evidence(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Rule 4: material claims must carry at least one evidence_id.

    A decision-driving claim (verified foundation fact or a recommendation /
    metrics / value output) with no evidence is an unsupported assertion the
    report must not lean on. Pure assumptions are excluded (see
    :func:`is_material`).
    """
    violations: list[GuardrailViolation] = []
    for c in claims:
        if is_material(c) and not c.evidence_ids:
            violations.append(
                GuardrailViolation(
                    rule=GuardrailRule.MATERIAL_EVIDENCE,
                    field_key=c.field_key,
                    message=(
                        f"{c.field_key!r} is material (kind={c.kind.value!r}, "
                        f"namespace={c.namespace!r}) but carries no evidence_ids — "
                        "a decision-driving claim must be backed by at least one "
                        "evidence row before it reaches the report."
                    ),
                )
            )
    return tuple(violations)


def check_contradiction_review(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Rule 5: contradictions surface for human review.

    A ``kind=contradiction`` claim means two authorities disagree; the report
    must not hide the disagreement behind a confident number. These violations
    carry ``requires_human_review=True`` — they are escalations, not integrity
    failures (the log may be consistent; it just needs adjudication).
    """
    violations: list[GuardrailViolation] = []
    for c in claims:
        if c.kind == ClaimKind.CONTRADICTION:
            rivals = c.metadata.get("contradicts", ())
            rival_str = ", ".join(rivals) if rivals else "(none named)"
            violations.append(
                GuardrailViolation(
                    rule=GuardrailRule.CONTRADICTION_REVIEW,
                    field_key=c.field_key,
                    message=(
                        f"{c.field_key!r} is kind=contradiction (rivals: {rival_str}) — "
                        "two authorities disagree; a human must adjudicate before the "
                        "report commits to a number. Never render as a settled fact."
                    ),
                    requires_human_review=True,
                )
            )
    return tuple(violations)


# All five rules, in declaration order. evaluate_guardrails applies them in
# this order so violation output is stable/deterministic.
_ALL_RULES: tuple = (
    check_local_authority_origin,
    check_assumption_namespace,
    check_hypothesis_verification,
    check_material_evidence,
    check_contradiction_review,
)


def evaluate_guardrails(claims: "Sequence[Claim]") -> tuple[GuardrailViolation, ...]:
    """Run all 5 guardrails over ``claims``; return every violation found.

    Deterministic: same claim set → same violations in the same order
    (rules applied in declaration order; within a rule, claims scanned in
    sequence order). Empty tuple → the log is report-clean (no integrity
    failures AND nothing requiring human review).
    """
    out: list[GuardrailViolation] = []
    for rule_fn in _ALL_RULES:
        out.extend(rule_fn(claims))
    return tuple(out)


def integrity_violations(
    violations: "Sequence[GuardrailViolation]",
) -> tuple[GuardrailViolation, ...]:
    """Filter ``violations`` to data-integrity failures (rules 1–4).

    The complement of :func:`human_review_violations`. A non-empty result
    means the claim log is internally inconsistent and must NOT be rendered
    as a report without repair.
    """
    return tuple(v for v in violations if not v.requires_human_review)


def human_review_violations(
    violations: "Sequence[GuardrailViolation]",
) -> tuple[GuardrailViolation, ...]:
    """Filter ``violations`` to escalations needing a human (rule 5).

    A non-empty result does NOT mean the log is broken — only that a
    contradiction must be adjudicated before the report commits to a number.
    """
    return tuple(v for v in violations if v.requires_human_review)


def requires_human_review(claims: "Sequence[Claim]") -> bool:
    """Does ``claims`` contain anything needing human adjudication?

    True iff a contradiction is present (rule 5 fires). Convenience over
    ``bool(human_review_violations(evaluate_guardrails(claims)))``.
    """
    return any(c.kind == ClaimKind.CONTRADICTION for c in claims)
