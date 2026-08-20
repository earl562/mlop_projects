"""Source authority models (Phase 1 — master spec §5, §7).

The ingestion unit is a JurisdictionSourceAuthority: a typed, provenance-backed
source for one jurisdiction's zoning/land-development code. Provider-agnostic —
covers Municode, eCode360, American Legal, Code Publishing, official PDF/HTML,
ArcGIS, manual. Never "a city" alone; always a (jurisdiction, scope, provider).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Provider(str, Enum):
    """Where the ordinance text comes from. Master spec §5 provider priority."""

    OFFICIAL_HTML = "official_html"
    OFFICIAL_PDF = "official_pdf"
    MUNICODE = "municode"
    ECODE360 = "ecode360"
    AMLEGAL = "amlegal"
    CODEPUBLISHING = "codepublishing"
    MUNICIPAL_CODES = "municipal_codes"
    ENCODEPLUS = "encodeplus"
    ARCGIS = "arcgis"
    MANUAL = "manual"


class JurisdictionType(str, Enum):
    COUNTY = "county"
    MUNICIPALITY = "municipality"
    SPECIAL_DISTRICT = "special_district"


class AuthorityScope(str, Enum):
    """What kind of regulation the authority covers."""

    ZONING = "zoning"
    LAND_DEVELOPMENT = "land_development"
    CODE_OF_ORDINANCES = "code_of_ordinances"
    GIS_ZONING = "gis_zoning"
    OVERLAYS = "overlays"
    COMP_PLAN = "comp_plan"
    ADOPTED_ORDINANCES = "adopted_ordinances"


class OfficialStatus(str, Enum):
    """Master spec §5: official | publisher_copy | informational | unknown."""

    OFFICIAL = "official"
    PUBLISHER_COPY = "publisher_copy"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


class FreshnessPolicy(str, Enum):
    LIVE_CHECK = "live_check"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


@dataclass
class JurisdictionSourceAuthority:
    """A typed, provenance-backed source authority for one jurisdiction.

    Master spec §5 + §7. The ingestion unit — not "a city" but a
    (jurisdiction, scope, provider) triple. Every ordinance citation derived
    from an authority carries its legal_caveat + freshness metadata.
    """

    state: str
    county: str
    municipality: str | None
    jurisdiction_type: JurisdictionType
    authority_scope: AuthorityScope
    provider: Provider
    canonical_url: str
    source_url: str
    source_title: str
    official_status: OfficialStatus
    legal_caveat: str
    id: str = ""
    jurisdiction_type_value: str = ""
    # Optional provenance / freshness (spec §5 fields)
    authority_scope_value: str = ""
    provider_value: str = ""
    official_status_value: str = ""
    freshness_policy: FreshnessPolicy = FreshnessPolicy.MONTHLY
    last_checked_at: str | None = None
    last_ingested_at: str | None = None
    source_version: str | None = None
    supplement_number: str | None = None
    effective_date: str | None = None
    ingestion_status: str = "pending"
    coverage_score: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Master spec §5 invariant: reject empty source URL (no authority without a source).
        if not self.source_url or not self.source_url.strip():
            raise ValueError(
                "JurisdictionSourceAuthority requires a non-empty source_url "
                "(no authority without a source)."
            )
        if not self.canonical_url or not self.canonical_url.strip():
            raise ValueError("JurisdictionSourceAuthority requires a non-empty canonical_url.")
        if not self.source_title or not self.source_title.strip():
            raise ValueError("JurisdictionSourceAuthority requires a non-empty source_title.")
        if not self.legal_caveat or not self.legal_caveat.strip():
            raise ValueError(
                "JurisdictionSourceAuthority requires a legal_caveat "
                "(every ordinance source must warn it may not be official/current)."
            )
        # Stash the enum values for DB persistence convenience.
        self.jurisdiction_type_value = self.jurisdiction_type.value
        self.authority_scope_value = self.authority_scope.value
        self.provider_value = self.provider.value
        self.official_status_value = self.official_status.value
        if not self.id:
            self.id = _authority_id(self)


def _authority_id(a: JurisdictionSourceAuthority) -> str:
    """Deterministic id: state-county-muni-scope-provider."""
    muni = (a.municipality or "unincorporated").lower().replace(" ", "_")
    return f"auth_{a.state.lower()}_{a.county.lower().replace(' ', '_')}_{muni}_{a.authority_scope.value}_{a.provider.value}"
