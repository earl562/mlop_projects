"""Shared transport-agnostic type contracts for the agentic harness.

These are the canonical payloads that REST routes, chat tools, and future MCP
adapters share so a tool result is always cited, replayable, and policy-aware.
They live in the domain layer (transport-free) so the harness, API, and
`land_use` service modules can all depend on a single source of truth without
creating an import cycle (`domain/` imports nothing from `land_use/`).

`land_use/models.py` re-exports these for backwards compatibility with existing
consumers; new code should import directly from `plotlot.domain.types`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

DEFAULT_ORDINANCE_LEGAL_CAVEAT = (
    "Online ordinance text may not be the official or most current copy; verify with the "
    "municipality or official clerk before taking legal, entitlement, or acquisition action."
)


class SourceType(StrEnum):
    """Evidence source categories used by reports and agent context."""

    ORDINANCE = "ordinance"
    ARCGIS_LAYER = "arcgis_layer"
    COUNTY_RECORD = "county_record"
    WEB_PAGE = "web_page"
    USER_DOCUMENT = "user_document"
    CONNECTOR_DOCUMENT = "connector_document"
    USER_PROVIDED = "user_provided"


class EvidenceConfidence(StrEnum):
    """Normalized confidence labels for evidence and layer mappings."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ToolRiskClass(StrEnum):
    """Risk classes used before executing tool calls."""

    READ_ONLY = "read_only"
    EXPENSIVE_READ = "expensive_read"
    WRITE_INTERNAL = "write_internal"
    WRITE_EXTERNAL = "write_external"
    EXECUTION = "execution"


class EvidenceCitation(BaseModel):
    """Source citation/provenance attached to every material evidence item."""

    model_config = ConfigDict(use_enum_values=True)

    source_type: SourceType
    title: str = Field(min_length=1)
    url: HttpUrl | None = None
    jurisdiction: str | None = None
    path: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    publisher: str | None = None
    legal_caveat: str | None = None
    raw_source_hash: str | None = None

    @field_validator("retrieved_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _add_ordinance_caveat(self) -> "EvidenceCitation":
        if self.source_type == SourceType.ORDINANCE and not self.legal_caveat:
            self.legal_caveat = DEFAULT_ORDINANCE_LEGAL_CAVEAT
        return self

    def display_label(self) -> str:
        """Human-readable label suitable for evidence rails and report footnotes."""

        parts = [self.title]
        if self.jurisdiction:
            parts.append(self.jurisdiction)
        if self.path:
            parts.append(" > ".join(self.path))
        return " — ".join(parts)


class EvidenceItem(BaseModel):
    """A normalized fact or source-backed observation produced by a tool run."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    tool_run_id: str | None = None
    claim_key: str = Field(min_length=1)
    payload: dict[str, Any]
    source_type: SourceType
    tool_name: str = Field(min_length=1)
    confidence: EvidenceConfidence
    citation: EvidenceCitation
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("retrieved_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _citation_must_match_source_type(self) -> "EvidenceItem":
        if self.citation.source_type != self.source_type:
            raise ValueError("citation.source_type must match evidence source_type")
        return self

    @property
    def value(self) -> dict[str, Any]:
        """Compatibility alias for earlier PRD examples that used `value`."""

        return self.payload


class ReportClaim(BaseModel):
    """A report claim that may require evidence support."""

    key: str = Field(min_length=1)
    text: str = Field(min_length=1)
    material: bool = True
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _material_claims_need_evidence(self) -> "ReportClaim":
        if self.material and not self.evidence_ids:
            raise ValueError("material report claims require at least one evidence_id")
        return self


class EvidenceBackedReportSection(BaseModel):
    """Report section that enforces evidence coverage for material claims."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    claims: list[ReportClaim] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _claim_refs_must_exist_in_section(self) -> "EvidenceBackedReportSection":
        known = set(self.evidence_ids)
        for claim in self.claims:
            missing = set(claim.evidence_ids) - known
            if missing:
                raise ValueError(f"claim {claim.key!r} references unknown evidence IDs: {missing}")
        return self


class ToolContext(BaseModel):
    """Execution context passed to every land-use tool."""

    workspace_id: str = Field(min_length=1)
    actor_user_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    tool_run_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    risk_budget_cents: int = Field(default=0, ge=0)
    live_network_allowed: bool = False
    approved_approval_ids: set[str] = Field(default_factory=set)


class PolicyDecision(BaseModel):
    """Decision returned before tool execution."""

    allowed: bool
    approval_required: bool = False
    reason: str = Field(min_length=1)
    approval_id: str | None = None

    @model_validator(mode="after")
    def _approval_id_required_when_needed(self) -> "PolicyDecision":
        if self.approval_required and not self.approval_id:
            raise ValueError("approval_id is required when approval_required is true")
        if self.allowed and self.approval_required:
            raise ValueError("a tool cannot be both allowed and approval_required")
        return self


class ToolContract(BaseModel):
    """Transport-agnostic contract for REST/chat/MCP tool adapters."""

    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    risk_class: ToolRiskClass
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    timeout_seconds: int = Field(default=30, ge=1)
    budget_cents: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        if not value.replace("_", "").replace(".", "").isalnum():
            raise ValueError("tool names may contain only letters, numbers, underscores, and dots")
        return value
