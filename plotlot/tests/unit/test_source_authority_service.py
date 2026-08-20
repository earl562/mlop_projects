"""Phase 2 TDD: source authority registry + provider priority (failing first).

Master spec §5 (provider priority), §8 (south_florida.py seeding),
§9 (provider-agnostic). Tests written BEFORE implementation.
"""

from __future__ import annotations


from plotlot.ingestion.source_authorities.models import (
    JurisdictionType,
    Provider,
)

# Fails until service.py + south_florida.py exist (TDD).
from plotlot.ingestion.source_authorities.service import (
    resolve_provider_priority,
    seed_south_florida_authorities,
)


class TestProviderPriority:
    """Master spec §5: official API/HTML > PDF > Municode > eCode360 > ..."""

    def test_official_html_beats_municode(self):
        official = Provider.OFFICIAL_HTML
        municode = Provider.MUNICODE
        assert resolve_provider_priority(official) < resolve_provider_priority(municode)

    def test_official_pdf_beats_municode(self):
        assert resolve_provider_priority(Provider.OFFICIAL_PDF) < resolve_provider_priority(
            Provider.MUNICODE
        )

    def test_municode_beats_amlegal(self):
        assert resolve_provider_priority(Provider.MUNICODE) < resolve_provider_priority(
            Provider.AMLEGAL
        )

    def test_amlegal_beats_manual(self):
        assert resolve_provider_priority(Provider.AMLEGAL) < resolve_provider_priority(
            Provider.MANUAL
        )

    def test_arcgis_is_lowest_priority_for_ordinance(self):
        # arcgis is gis_zoning, not ordinance text — lowest for ordinance scope.
        assert resolve_provider_priority(Provider.ARCGIS) > resolve_provider_priority(
            Provider.MUNICODE
        )


class TestSouthFloridaSeeding:
    """Master spec §5 special handling: counties, Miami21, PBC ULDC."""

    def test_seeds_three_counties(self):
        auths = seed_south_florida_authorities()
        counties = {a.county for a in auths}
        assert "Miami-Dade" in counties
        assert "Broward" in counties
        assert "Palm Beach" in counties

    def test_miami_dade_unincorporated_is_county_authority(self):
        auths = seed_south_florida_authorities()
        mdc = [a for a in auths if a.county == "Miami-Dade" and a.municipality is None]
        assert mdc, "Miami-Dade unincorporated must be a separate county authority"
        assert mdc[0].jurisdiction_type is JurisdictionType.COUNTY

    def test_city_of_miami_has_miami21_special_authority(self):
        auths = seed_south_florida_authorities()
        miami = [
            a
            for a in auths
            if a.municipality == "Miami"
            and "miami21" in (a.metadata_json.get("special", "").lower() or a.source_title.lower())
        ]
        assert miami, "City of Miami must have a Miami21 special authority"
        # Miami21 must carry a current-source caveat.
        assert (
            "caveat" in miami[0].legal_caveat.lower() or "current" in miami[0].legal_caveat.lower()
        )

    def test_palm_beach_uldc_special_authority(self):
        auths = seed_south_florida_authorities()
        pbc = [a for a in auths if a.county == "Palm Beach" and "uldc" in a.source_title.lower()]
        assert pbc, "Palm Beach County ULDC must be a special authority"

    def test_every_authority_has_legal_caveat(self):
        auths = seed_south_florida_authorities()
        for a in auths:
            assert a.legal_caveat.strip(), f"{a.municipality or a.county}: missing legal_caveat"
