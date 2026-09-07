"""South Florida source authorities (Phase 2 — master spec §5 special handling).

Seeds the authoritative jurisdictions: Miami-Dade, Broward, Palm Beach counties
+ incorporated municipalities + special authorities (City of Miami Miami21,
Palm Beach County ULDC, unincorporated county jurisdictions).
"""

from __future__ import annotations

from plotlot.ingestion.source_authorities.models import (
    AuthorityScope,
    JurisdictionSourceAuthority,
    JurisdictionType,
    OfficialStatus,
    Provider,
)

_LEGAL_CAVEAT_ORDINANCE = (
    "Online code may not be the official/current copy; verify with the "
    "municipality/county before entitlement or acquisition action."
)
_MIAMI21_CAVEAT = (
    "Miami21 is the form-based code; confirm current adoption + amendments with "
    "the City of Miami before action. Historical/educational text is not sole "
    "definitive authority."
)
_ULDC_CAVEAT = (
    "Palm Beach County ULDC: base code + adopted ordinances not yet codified "
    "are indexed separately; confirm supplement currency before action."
)


def _municode_authority(
    *,
    state: str,
    county: str,
    municipality: str | None,
    jurisdiction_type: JurisdictionType,
    authority_scope: AuthorityScope = AuthorityScope.ZONING,
    source_url: str,
    source_title: str,
    official_status: OfficialStatus = OfficialStatus.PUBLISHER_COPY,
    legal_caveat: str = _LEGAL_CAVEAT_ORDINANCE,
    metadata: dict | None = None,
) -> JurisdictionSourceAuthority:
    return JurisdictionSourceAuthority(
        state=state,
        county=county,
        municipality=municipality,
        jurisdiction_type=jurisdiction_type,
        authority_scope=authority_scope,
        provider=Provider.MUNICODE,
        canonical_url=source_url,
        source_url=source_url,
        source_title=source_title,
        official_status=official_status,
        legal_caveat=legal_caveat,
        metadata_json=metadata or {},
    )


def seed_south_florida_authorities() -> list[JurisdictionSourceAuthority]:
    """Seed the master spec §5 South Florida authority set.

    Three counties (unincorporated = county authority), City of Miami Miami21
    special authority, Palm Beach County ULDC special authority. Every authority
    carries a legal caveat.
    """
    auths: list[JurisdictionSourceAuthority] = []

    # ── County unincorporated jurisdictions (spec §5: separate from municipalities) ──
    auths.append(
        _municode_authority(
            state="FL",
            county="Miami-Dade",
            municipality=None,
            jurisdiction_type=JurisdictionType.COUNTY,
            source_url="https://library.municode.com/fl/miami_dade",
            source_title="Miami-Dade County Code of Ordinances",
        )
    )
    auths.append(
        _municode_authority(
            state="FL",
            county="Broward",
            municipality=None,
            jurisdiction_type=JurisdictionType.COUNTY,
            source_url="https://library.municode.com/fl/broward_county",
            source_title="Broward County Code of Ordinances",
        )
    )
    auths.append(
        _municode_authority(
            state="FL",
            county="Palm Beach",
            municipality=None,
            jurisdiction_type=JurisdictionType.COUNTY,
            source_url="https://library.municode.com/fl/palm_beach_county",
            source_title="Palm Beach County Code of Ordinances",
        )
    )

    # ── City of Miami / Miami21 (spec §5 special handling) ──
    auths.append(
        JurisdictionSourceAuthority(
            state="FL",
            county="Miami-Dade",
            municipality="Miami",
            jurisdiction_type=JurisdictionType.MUNICIPALITY,
            authority_scope=AuthorityScope.ZONING,
            provider=Provider.OFFICIAL_HTML,  # Miami21 is the city's form-based code
            canonical_url="https://www.miami.gov/government/city-planning/miami-21-zoning",
            source_url="https://www.miami.gov/government/city-planning/miami-21-zoning",
            source_title="Miami21 — City of Miami Form-Based Code",
            official_status=OfficialStatus.OFFICIAL,
            legal_caveat=_MIAMI21_CAVEAT,
            metadata_json={"special": "miami21"},
        )
    )

    # ── Palm Beach County ULDC (spec §5 special handling: base + adopted) ──
    auths.append(
        JurisdictionSourceAuthority(
            state="FL",
            county="Palm Beach",
            municipality=None,
            jurisdiction_type=JurisdictionType.COUNTY,
            authority_scope=AuthorityScope.LAND_DEVELOPMENT,
            provider=Provider.OFFICIAL_PDF,  # ULDC base is PDF-supplemented
            canonical_url="https://www.pbcgov.org/pzb/planing/uldc",
            source_url="https://www.pbcgov.org/pzb/planing/uldc",
            source_title="Palm Beach County Unified Land Development Code (ULDC)",
            official_status=OfficialStatus.OFFICIAL,
            legal_caveat=_ULDC_CAVEAT,
            metadata_json={"special": "uldc"},
        )
    )
    # Adopted ordinances not yet codified (indexed separately, spec §5).
    auths.append(
        JurisdictionSourceAuthority(
            state="FL",
            county="Palm Beach",
            municipality=None,
            jurisdiction_type=JurisdictionType.COUNTY,
            authority_scope=AuthorityScope.ADOPTED_ORDINANCES,
            provider=Provider.OFFICIAL_PDF,
            canonical_url="https://www.pbcgov.org/pzb/planing/ordinances",
            source_url="https://www.pbcgov.org/pzb/planing/ordinances",
            source_title="Palm Beach County Adopted Ordinances (not yet codified)",
            official_status=OfficialStatus.OFFICIAL,
            legal_caveat=_ULDC_CAVEAT,
            metadata_json={"special": "uldc_adopted"},
        )
    )

    return auths
