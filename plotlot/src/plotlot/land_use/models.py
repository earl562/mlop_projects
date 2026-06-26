"""Service-specific typed contracts for PlotLot's land-use layer.

The shared transport-agnostic contracts (`EvidenceCitation`, `EvidenceItem`,
`ReportClaim`, `ToolContract`, `ToolContext`, `PolicyDecision`, etc.) have moved
to `plotlot.domain.types` — the domain layer is transport-free and `land_use/`
now depends on it rather than owning those primitives itself. This module
re-exports them for backwards compatibility with existing consumers and keeps
only the ordinance/layer query types that are land-use-service-specific.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from plotlot.domain.types import (
    DEFAULT_ORDINANCE_LEGAL_CAVEAT,
    EvidenceBackedReportSection,
    EvidenceCitation,
    EvidenceConfidence,
    EvidenceItem,
    PolicyDecision,
    ReportClaim,
    SourceType,
    ToolContext,
    ToolContract,
    ToolRiskClass,
)

__all__ = [
    "DEFAULT_ORDINANCE_LEGAL_CAVEAT",
    "EvidenceBackedReportSection",
    "EvidenceCitation",
    "EvidenceConfidence",
    "EvidenceItem",
    "LayerCandidate",
    "OrdinanceJurisdiction",
    "OrdinanceSearchArgs",
    "OrdinanceSearchResult",
    "PolicyDecision",
    "PropertyLayerQuery",
    "ReportClaim",
    "SourceType",
    "ToolContext",
    "ToolContract",
    "ToolRiskClass",
]


class OrdinanceJurisdiction(BaseModel):
    """Jurisdiction selector for ordinance tools."""

    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    municipality: str | None = None

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _require_county_or_municipality(self) -> "OrdinanceJurisdiction":
        if not self.county and not self.municipality:
            raise ValueError("county or municipality is required")
        return self

    def label(self) -> str:
        parts = [p for p in [self.municipality, self.county, self.state] if p]
        return ", ".join(parts)


class OrdinanceSearchArgs(BaseModel):
    """Input for ordinance search."""

    jurisdiction: OrdinanceJurisdiction
    query: str = Field(min_length=1)
    limit: int = Field(default=8, ge=1, le=25)
    include_text_snippets: bool = True


class OrdinanceSearchResult(BaseModel):
    """Cited ordinance search/fetch result."""

    section_id: str | None = None
    heading: str = Field(min_length=1)
    path: list[str] = Field(default_factory=list)
    snippet: str = Field(min_length=1)
    citation: EvidenceCitation
    evidence_id: str | None = None

    @model_validator(mode="after")
    def _must_be_ordinance_citation(self) -> "OrdinanceSearchResult":
        if self.citation.source_type != SourceType.ORDINANCE:
            raise ValueError("ordinance results require an ordinance citation")
        return self


LayerType = Literal[
    "parcel",
    "zoning",
    "land_use",
    "utility",
    "environment",
    "transportation",
    "economic_development",
    "unknown",
]


class LayerCandidate(BaseModel):
    """Normalized OpenData/ArcGIS layer candidate."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: HttpUrl
    service_url: HttpUrl
    layer_id: int | None = Field(default=None, ge=0)
    layer_type: LayerType = "unknown"
    evidence_id: str | None = None
    publisher: str | None = None
    update_frequency: str | None = None
    field_mapping_confidence: EvidenceConfidence = EvidenceConfidence.UNKNOWN
    citation: EvidenceCitation

    @model_validator(mode="after")
    def _must_be_arcgis_citation(self) -> "LayerCandidate":
        if self.citation.source_type != SourceType.ARCGIS_LAYER:
            raise ValueError("layer candidates require an ArcGIS layer citation")
        return self


class PropertyLayerQuery(BaseModel):
    """Canonical query shape for parcel/zoning/owner layers."""

    county: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    address: str | None = None
    apn: str | None = None
    owner: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    out_fields: list[str] = Field(default_factory=lambda: ["*"])
    limit: int = Field(default=50, ge=1, le=1000)

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _require_query_selector(self) -> "PropertyLayerQuery":
        if not any([self.address, self.apn, self.owner, self.bbox]):
            raise ValueError("address, apn, owner, or bbox is required")
        return self
