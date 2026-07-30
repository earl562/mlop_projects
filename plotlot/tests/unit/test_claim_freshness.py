"""Slice 3.4 contract tests: freshness as a typed claim property.

Pins the 3.4 acceptance criteria:
  * A chunk whose amended_date > scraped_at produces freshness=stale on the
    derived Claim (criterion 1).
  * A stale zoning.* Claim cannot satisfy a verified_fact prerequisite — the
    planner/guardrail blocks it via satisfies_verified_fact_prerequisite (criterion 2).
  * Contract test: a stale chunk yields freshness=stale; a fresh chunk yields
    freshness=fresh (criterion 3).

Kleyman: 'refresh before relying'. Enforced at the claim layer.
"""

from __future__ import annotations


from plotlot.domain.claims import (
    Claim,
    ClaimFreshness,
    ClaimKind,
    ClaimOrigin,
)


def _verified_zoning_claim(metadata=None):
    return Claim(
        field_key="zoning.district",
        value="RS-8",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        metadata=metadata or {},
    )


class TestFreshnessDerivation:
    """Criterion 1: amended_date > scraped_at → freshness=stale."""

    def test_stale_chunk_yields_stale_freshness(self):
        # Ordinance amended 2026-06-01, scraped 2026-01-01 → stale.
        claim = _verified_zoning_claim(
            {
                "amended_date": "2026-06-01T00:00:00",
                "scraped_at": "2026-01-01T00:00:00",
            }
        )
        assert claim.freshness is ClaimFreshness.STALE

    def test_fresh_chunk_yields_fresh_freshness(self):
        # Ordinance amended 2026-01-01, scraped 2026-06-01 → fresh.
        claim = _verified_zoning_claim(
            {
                "amended_date": "2026-01-01T00:00:00",
                "scraped_at": "2026-06-01T00:00:00",
            }
        )
        assert claim.freshness is ClaimFreshness.FRESH

    def test_no_dates_yields_unknown_freshness(self):
        claim = _verified_zoning_claim({})
        assert claim.freshness is ClaimFreshness.UNKNOWN

    def test_only_one_date_yields_unknown_freshness(self):
        claim = _verified_zoning_claim({"amended_date": "2026-06-01T00:00:00"})
        assert claim.freshness is ClaimFreshness.UNKNOWN

    def test_equal_dates_yield_fresh(self):
        # amended == scraped → we have the current version.
        claim = _verified_zoning_claim(
            {
                "amended_date": "2026-06-01T00:00:00",
                "scraped_at": "2026-06-01T00:00:00",
            }
        )
        assert claim.freshness is ClaimFreshness.FRESH

    def test_malformed_dates_fall_back_to_unknown(self):
        claim = _verified_zoning_claim(
            {
                "amended_date": "not-a-date",
                "scraped_at": "2026-01-01T00:00:00",
            }
        )
        assert claim.freshness is ClaimFreshness.UNKNOWN


class TestVerifiedFactPrerequisite:
    """Criterion 2: a stale zoning.* Claim cannot satisfy a verified_fact
    prerequisite; the planner/guardrail blocks it."""

    def test_fresh_verified_fact_satisfies_prerequisite(self):
        claim = _verified_zoning_claim(
            {
                "amended_date": "2026-01-01T00:00:00",
                "scraped_at": "2026-06-01T00:00:00",
            }
        )
        assert claim.satisfies_verified_fact_prerequisite() is True

    def test_stale_verified_fact_does_not_satisfy_prerequisite(self):
        claim = _verified_zoning_claim(
            {
                "amended_date": "2026-06-01T00:00:00",
                "scraped_at": "2026-01-01T00:00:00",
            }
        )
        assert claim.freshness is ClaimFreshness.STALE
        # A stale verified_fact cannot satisfy the prerequisite — the planner
        # must block step 5 (residual land value) until re-ingested.
        assert claim.satisfies_verified_fact_prerequisite() is False

    def test_unknown_freshness_verified_fact_satisfies_prerequisite(self):
        # No freshness info → cannot prove stale → allowed (conservative allow
        # when freshness is unknown; the planner treats unknown as not-stale).
        claim = _verified_zoning_claim({})
        assert claim.freshness is ClaimFreshness.UNKNOWN
        assert claim.satisfies_verified_fact_prerequisite() is True

    def test_assumption_never_satisfies_verified_prerequisite(self):
        claim = Claim(
            field_key="assumed_zoning.district",
            value="RS-8",
            kind=ClaimKind.ASSUMPTION,
            origin=ClaimOrigin.UNKNOWN,
            confidence=0.4,
            metadata={"amended_date": "2026-01-01", "scraped_at": "2026-06-01"},
        )
        # Fresh, but not a verified_fact → never satisfies the prerequisite.
        assert claim.freshness is ClaimFreshness.FRESH
        assert claim.satisfies_verified_fact_prerequisite() is False

    def test_hypothesis_never_satisfies_verified_prerequisite(self):
        claim = Claim(
            field_key="opportunity.lot_split",
            value=True,
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.UNKNOWN,
            confidence=0.3,
            next_verification_step="confirm lot-split eligibility with planner",
        )
        assert claim.satisfies_verified_fact_prerequisite() is False
