"""Tests for deterministic CA density uplift (ADU / SB9 / Density Bonus)."""

from plotlot.pipeline.density_bonus import _density_bonus_fraction, compute_density_uplift


def _program(uplift, name):
    return next((p for p in uplift.programs if p.name == name), None)


class TestCaliforniaGating:
    def test_non_ca_returns_empty(self):
        u = compute_density_uplift(10, state="FL")
        assert u.programs == []
        assert u.max_potential_units == 0
        assert any("California only" in n for n in u.notes)

    def test_zero_base_units(self):
        u = compute_density_uplift(0, state="CA")
        assert u.programs == []


class TestSingleFamily:
    def test_sfr_gets_adu_and_sb9(self):
        u = compute_density_uplift(1, state="CA", property_type="single_family")
        adu = _program(u, "ADU + JADU")
        sb9 = _program(u, "SB9 lot split + duplex")
        assert adu.potential_units == 3  # 1 + ADU + JADU
        assert sb9.potential_units == 4  # lot split → 2 lots × 2 units
        assert u.max_potential_units == 4
        # Density Bonus does NOT apply to a 1-unit project (needs 5+).
        assert _program(u, "Density Bonus") is None

    def test_base_one_is_treated_as_sfr(self):
        u = compute_density_uplift(1, state="CA")
        assert _program(u, "SB9 lot split + duplex") is not None


class TestMultifamily:
    def test_small_mf_adu_only_no_density_bonus(self):
        # 4 units < 5 → Density Bonus Law doesn't apply.
        u = compute_density_uplift(4, state="CA", property_type="multifamily")
        assert _program(u, "ADU (detached)").potential_units == 6
        assert _program(u, "Density Bonus") is None
        assert _program(u, "SB9 lot split + duplex") is None
        assert u.max_potential_units == 6

    def test_mf_5plus_gets_default_max_density_bonus(self):
        u = compute_density_uplift(10, state="CA", property_type="multifamily")
        db = _program(u, "Density Bonus")
        assert db.additional_units == 5  # floor(10 × 0.50)
        assert db.potential_units == 15
        assert "65915" in db.statute
        assert u.max_potential_units == 15  # best pathway (vs ADU's 12)

    def test_density_bonus_with_explicit_set_aside(self):
        # 10% low-income → 20% bonus (statutory tier minimum).
        u = compute_density_uplift(
            20, state="CA", property_type="multifamily", income_level="low", set_aside_pct=10
        )
        db = _program(u, "Density Bonus")
        assert db.additional_units == 4  # floor(20 × 0.20)


class TestSiteHazardEligibility:
    def test_sb9_restricted_in_flood_zone(self):
        u = compute_density_uplift(
            1, state="CA", property_type="single_family", in_flood_hazard=True
        )
        sb9 = _program(u, "SB9 lot split + duplex")
        assert sb9.eligibility == "restricted"
        assert "Flood Hazard" in sb9.requirements
        # restricted SB9 must NOT drive the headline upside → ADU's 3 wins
        assert u.max_potential_units == 3
        assert any("restricted" in n.lower() for n in u.notes)

    def test_sb9_restricted_by_wetlands(self):
        u = compute_density_uplift(1, state="CA", property_type="single_family", has_wetlands=True)
        assert _program(u, "SB9 lot split + duplex").eligibility == "restricted"

    def test_no_hazard_sb9_eligible(self):
        u = compute_density_uplift(1, state="CA", property_type="single_family")
        assert _program(u, "SB9 lot split + duplex").eligibility == "eligible"
        assert u.max_potential_units == 4

    def test_flood_does_not_restrict_adu_or_density_bonus(self):
        # Flood zone excludes SB9 but NOT ADU/Density Bonus (allowed, just costlier).
        u = compute_density_uplift(
            10, state="CA", property_type="multifamily", in_flood_hazard=True
        )
        assert _program(u, "ADU (detached)").eligibility == "eligible"
        assert _program(u, "Density Bonus").eligibility == "eligible"
        assert u.max_potential_units == 15  # density bonus unaffected


class TestDensityBonusFraction:
    def test_very_low_endpoints(self):
        assert _density_bonus_fraction("very_low", 5) == 0.20
        assert _density_bonus_fraction("very_low", 15) == 0.50

    def test_low_endpoints(self):
        assert _density_bonus_fraction("low", 10) == 0.20
        assert _density_bonus_fraction("low", 24) == 0.50

    def test_below_threshold_returns_none(self):
        assert _density_bonus_fraction("very_low", 3) is None
        assert _density_bonus_fraction("low", 8) is None

    def test_above_max_caps(self):
        assert _density_bonus_fraction("very_low", 30) == 0.50

    def test_unknown_level_none(self):
        assert _density_bonus_fraction("bogus", 20) is None


class TestProvenanceAndDeterminism:
    def test_provisional_base_flagged(self):
        u = compute_density_uplift(10, state="CA", base_is_provisional=True)
        assert any("provisional" in n.lower() for n in u.notes)

    def test_attorney_caveat_always_present(self):
        u = compute_density_uplift(10, state="CA")
        assert any("attorney" in n.lower() for n in u.notes)

    def test_deterministic(self):
        runs = [
            compute_density_uplift(10, state="CA", property_type="multifamily").max_potential_units
            for _ in range(20)
        ]
        assert all(r == runs[0] for r in runs)

    def test_base_count_never_mutated(self):
        # The firm base count is preserved, not folded into the programs.
        u = compute_density_uplift(8, state="CA", property_type="multifamily")
        assert u.base_units == 8
