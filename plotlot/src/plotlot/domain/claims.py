"""Typed claims — the spine of the agentic harness.

Every fact the agent reasons over is a `Claim`: a typed, provenanced assertion
that carries its `kind` (epistemic status) and `origin` (where it came from).
The Kleyman 8-step methodology, the source-boundary rule (Rehab Valuator corpus
is authoritative for concepts, NOT for local facts), and the report's
verified/assumption/hypothesis rendering all hang off these two fields.

This module is transport-free: pure data + invariants. Nothing here imports
from harness/, api/, tools/, or retrieval/.

Slice 2.1 — the typed-claim spine. Later slices (`steps.py`, `guardrails.py`)
build rules *over* these types; this slice only defines them + the one
invariant they all share: `source_boundary_ok`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ClaimKind(str, Enum):
    """Epistemic status of a claim.

    Ordering matters for the verification ladder:
    hypothesis → assumption → verified_fact (promotion),
    verified_fact → assumption (demotion on staleness/boundary breach).
    `calculation` is a derived kind: provable from inputs + formula, but it
    inherits the trust of its inputs (a calc over assumptions is assumption-grade
    at best, never silently promoted to verified_fact).
    `contradiction` is terminal: two claims disagree; surface to human review.
    """

    VERIFIED_FACT = "verified_fact"  # grounded in local authority (ordinance, county record)
    ASSUMPTION = "assumption"  # asserted but unverified; rendered amber
    HYPOTHESIS = "hypothesis"  # speculative upside; needs next_verification_step
    CALCULATION = "calculation"  # derived from other claims via a formula
    CONTRADICTION = "contradiction"  # two claims disagree; requires_human_review


class ClaimOrigin(str, Enum):
    """Where a claim's truth comes from. Enforces the source boundary.

    The Rehab Valuator corpus is authoritative for underwriting *concepts*
    (the 8-step workflow, financing logic) but NOT for local facts (parcel
    facts, zoning, ordinances, local costs, cap rates). A concept from the
    corpus must be `origin=rehabvaluator_concept`, never `local_authority`.
    """

    LOCAL_AUTHORITY = "local_authority"  # .gov ordinance, county ArcGIS record, deed
    REHABVALUATOR_CONCEPT = "rehabvaluator_concept"  # from the corpus (concepts only)
    USER_PROVIDED = "user_provided"  # the human stated it; respected but flagged
    DERIVED_CALC = "derived_calc"  # produced by a calculator from other claims
    UNKNOWN = "unknown"  # origin unproven (e.g. scraped comps); confidence ceiling


# Field-key namespaces whose truth MUST come from a local authority.
# A claim in one of these namespaces with origin != LOCAL_AUTHORITY is a
# source-boundary violation (the Rehab Valuator corpus is not a zoning oracle).
# Public so guardrails.py validates loaded/aggregated claim sets against the
# SAME boundary the Claim constructor enforces (no drift).
LOCAL_AUTHORITY_NAMESPACES: frozenset[str] = frozenset(
    {
        "zoning",  # zoning.district, zoning.setback_front_ft, ...
        "parcel",  # parcel.lot_area_sqft, parcel.apn, ...
    }
)

# Field-key namespaces whose truth MUST NOT be presented as a verified fact.
# Costs, cap rates, and financing terms are always assumptions (market-derived
# or user-supplied) — never a verified_fact grounded in a local authority.
ASSUMPTION_NAMESPACES: frozenset[str] = frozenset(
    {
        "cost",  # cost.hard_per_sqft, cost.soft_per_sqft
        "cap_rate",  # cap_rate.market
        "financing",  # financing.construction_ltc, financing.perm_rate
        "rent",  # rent.market_per_unit
    }
)


class SourceBoundaryViolation(Exception):
    """Raised when a claim's origin/kind combination breaks the source boundary.

    This is the invariant the whole harness is built on: a `zoning.*` claim
    with `origin=rehabvaluator_concept` (or anything other than local_authority)
    is a *validation failure*, not a warning — the corpus is not a zoning oracle.
    Likewise a `cost.*` claim with `kind=verified_fact` claims a local market
    number is a verified fact, which the corpus cannot ground.
    """


class ClaimFreshness(str, Enum):
    """Freshness of a claim's backing source vs. when it was scraped.

    Kleyman: 'refresh before relying'. A claim derived from a source chunk whose
    amended_date is newer than scraped_at is STALE — the ordinance was amended
    after we ingested it, so the claim may no longer reflect the current law.
    A stale verified_fact cannot satisfy a planner prerequisite (it must be
    re-ingested or demoted to assumption).
    """

    FRESH = "fresh"  # scraped_at >= amended_date (we have the current version)
    STALE = "stale"  # amended_date > scraped_at (ordinance amended since ingest)
    UNKNOWN = "unknown"  # no amended_date / scraped_at available


@dataclass(frozen=True, slots=True)
class Claim:
    """A typed, provenanced assertion.

    Attributes:
        field_key: namespaced dotted key, e.g. ``zoning.district``,
            ``cost.hard_per_sqft``. The namespace (prefix before the first dot)
            drives the source-boundary rules.
        value: the asserted value (str, float, int, bool, or nested mapping).
        kind: epistemic status — see :class:`ClaimKind`.
        origin: where the truth comes from — see :class:`ClaimOrigin`.
        confidence: 0.0–1.0. Capped for non-verified claims (e.g. scraped comps
            at origin=unknown are capped ≤ 0.5). ``None`` means unset.
        evidence_ids: ids of evidence rows backing this claim. Material claims
            (those that change the go/no-go) must carry at least one; the report
            validator enforces this in a later slice.
        source_url: URL of the authority page/record (for local_authority /
            unknown origins). Empty for pure concepts/calcs.
        next_verification_step: required for ``kind=HYPOTHESIS`` — how to
            promote/demote it. The report renders hypotheses distinctly and
            forbids presenting entitlement upside as guaranteed.
        extracted_at: ISO timestamp of extraction (for freshness, slice 3.4).
        freshness: FRESH / STALE / UNKNOWN. STALE when the backing source's
            amended_date > scraped_at (the ordinance was amended after we
            ingested it). A stale verified_fact in a local-authority namespace
            is demoted — it cannot satisfy a planner prerequisite.
        metadata: freeform bag for tool-specific provenance (layer id, query,
            page number). Never carries truth — only breadcrumbs. Carries
            amended_date / scraped_at (ISO 8601) for freshness derivation.
    """

    field_key: str
    value: Any
    kind: ClaimKind
    origin: ClaimOrigin
    confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()
    source_url: str = ""
    next_verification_step: str = ""
    extracted_at: str = ""
    freshness: ClaimFreshness = ClaimFreshness.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        namespace = _namespace(self.field_key)
        # 1. Local-authority namespaces (zoning.*, parcel.*) must originate
        #    from a local authority. The corpus (rehabvaluator_concept),
        #    user input, derivation, and unknown origins cannot ground them.
        if namespace in LOCAL_AUTHORITY_NAMESPACES and self.origin != ClaimOrigin.LOCAL_AUTHORITY:
            raise SourceBoundaryViolation(
                f"field_key={self.field_key!r} is in a local-authority namespace "
                f"({namespace!r}); origin={self.origin.value!r} cannot ground it. "
                "Only origin=local_authority may assert zoning.* / parcel.* facts "
                "(the Rehab Valuator corpus is not a zoning oracle)."
            )
        # 2. Assumption namespaces (cost.*, cap_rate, financing.*, rent.*)
        #    must never be verified_fact — market numbers are not grounded in
        #    a local authority the way an ordinance is.
        if namespace in ASSUMPTION_NAMESPACES and self.kind == ClaimKind.VERIFIED_FACT:
            raise SourceBoundaryViolation(
                f"field_key={self.field_key!r} is in an assumption namespace "
                f"({namespace!r}); kind=verified_fact is forbidden — "
                "costs/cap rates/financing terms are always assumptions."
            )
        # 3. Hypotheses must declare how they'll be verified/promoted.
        if self.kind == ClaimKind.HYPOTHESIS and not self.next_verification_step:
            raise SourceBoundaryViolation(
                f"field_key={self.field_key!r} is kind=hypothesis but has no "
                "next_verification_step — entitlement upside must state how it "
                "would be promoted or demoted."
            )
        # 4. Contradictions must carry evidence of both sides (so a human can
        #    adjudicate). The metadata["contradicts"] key holds the rival ids.
        if self.kind == ClaimKind.CONTRADICTION and not self.metadata.get("contradicts"):
            raise SourceBoundaryViolation(
                f"field_key={self.field_key!r} is kind=contradiction but carries "
                "no 'contradicts' metadata — a contradiction must name both sides."
            )
        # 5. Unknown-origin claims are confidence-capped (scraped comps, etc.).
        if (
            self.origin == ClaimOrigin.UNKNOWN
            and self.confidence is not None
            and self.confidence > 0.5
        ):
            raise SourceBoundaryViolation(
                f"field_key={self.field_key!r} has origin=unknown but "
                f"confidence={self.confidence} > 0.5 — unknown-origin claims are "
                "capped at 0.5 (scraped comps are amber, never authoritative)."
            )
        # 6. Freshness derivation (Slice 3.4): if metadata carries amended_date
        #    and scraped_at (ISO 8601), a source amended AFTER it was scraped is
        #    STALE. Kleyman 'refresh before relying' — a stale verified_fact may
        #    no longer reflect current law.
        amended = self.metadata.get("amended_date")
        scraped = self.metadata.get("scraped_at")
        if amended and scraped:
            try:
                from datetime import datetime, timezone

                a = datetime.fromisoformat(str(amended))
                s = datetime.fromisoformat(str(scraped))
                # Normalize to offset-aware (UTC) so naive vs aware dates compare.
                if a.tzinfo is None:
                    a = a.replace(tzinfo=timezone.utc)
                if s.tzinfo is None:
                    s = s.replace(tzinfo=timezone.utc)
                if a > s:
                    object.__setattr__(self, "freshness", ClaimFreshness.STALE)
                else:
                    object.__setattr__(self, "freshness", ClaimFreshness.FRESH)
            except (ValueError, TypeError):
                # Malformed dates → leave freshness as passed (UNKNOWN by default).
                pass
        elif amended or scraped:
            # Only one of the two present → cannot determine freshness.
            object.__setattr__(self, "freshness", ClaimFreshness.UNKNOWN)

    @property
    def namespace(self) -> str:
        """The field-key prefix (before the first dot). Drives boundary rules."""
        return _namespace(self.field_key)

    def satisfies_verified_fact_prerequisite(self) -> bool:
        """Can this claim satisfy a planner prerequisite requiring verified_fact?

        A verified_fact claim in a local-authority namespace satisfies the
        prerequisite ONLY when fresh. A stale verified_fact (ordinance amended
        since ingestion) does NOT — Kleyman 'refresh before relying' — it must
        be re-ingested or treated as an assumption. Non-verified claims never
        satisfy a verified_fact prerequisite regardless of freshness.
        """
        if self.kind is not ClaimKind.VERIFIED_FACT:
            return False
        if self.freshness is ClaimFreshness.STALE:
            return False
        return True


def source_boundary_ok(claim: Claim) -> bool:
    """Pure invariant check: does ``claim`` satisfy the source boundary?

    Returns ``True`` if the claim was constructible without raising
    :class:`SourceBoundaryViolation` (the constructor already enforces it,
    so this is a re-check / predicate form for use in guardrail rules and
    report validators). Construction-time enforcement means any ``Claim``
    that exists in memory is boundary-ok by construction; this predicate
    exists so downstream rules can assert it defensively over loaded/serialized
    claim rows without re-running ``__post_init__`` side effects.
    """
    namespace = _namespace(claim.field_key)
    if namespace in LOCAL_AUTHORITY_NAMESPACES and claim.origin != ClaimOrigin.LOCAL_AUTHORITY:
        return False
    if namespace in ASSUMPTION_NAMESPACES and claim.kind == ClaimKind.VERIFIED_FACT:
        return False
    if claim.kind == ClaimKind.HYPOTHESIS and not claim.next_verification_step:
        return False
    if claim.kind == ClaimKind.CONTRADICTION and not claim.metadata.get("contradicts"):
        return False
    if (
        claim.origin == ClaimOrigin.UNKNOWN
        and claim.confidence is not None
        and claim.confidence > 0.5
    ):
        return False
    return True


def _namespace(field_key: str) -> str:
    """Extract the namespace prefix (before the first ``.``).

    ``"zoning.district"`` → ``"zoning"``; a bare ``"cap_rate"`` (no dot) →
    ``"cap_rate"``. An empty key returns ``""`` (no namespace → no rule fires).
    """
    if not field_key:
        return ""
    return field_key.split(".", 1)[0]
