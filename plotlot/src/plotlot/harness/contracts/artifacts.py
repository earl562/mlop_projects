from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from plotlot.harness.contracts.base import (
    ApplicabilityScope,
    ApplicabilityStatus,
    ApprovalId,
    ApprovalStatus,
    AssumptionId,
    ClaimFreshnessStatus,
    ClaimId,
    ClaimKind,
    ClaimOrigin,
    ClaimStatus,
    CountyName,
    EvidenceId,
    EvidenceSourceType,
    FreshnessStatus,
    GISProvider,
    HarnessContract,
    JsonObject,
    MemoryId,
    MemoryType,
    ProjectId,
    ReportId,
    ReportStatus,
    ReportType,
    RiskLevel,
    RunId,
    SiteId,
    SourceLane,
    SourceMode,
    ToolCallId,
    TrainingConceptId,
    TranscriptSegmentId,
    VerificationId,
    VerificationStatus,
    WorkspaceId,
    utc_now,
)


class SourceCatalogEntry(HarnessContract):
    source_id: str = Field(min_length=1)
    lane: SourceLane
    provider: GISProvider | str
    source_type: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    county: CountyName | None = None
    municipality: str | None = None
    dataset_name: str = Field(min_length=1)
    layer_name: str | None = None
    source_url: str = Field(min_length=1)
    item_url: str | None = None
    feature_service_url: str | None = None
    code_url: str | None = None
    geometry_type: str | None = None
    update_frequency: str | None = None
    freshness_policy: str = "verify_metadata_timestamp"
    applicability_scope: ApplicabilityScope = ApplicabilityScope.UNKNOWN
    access_status: str = "public"
    enabled: bool = True
    metadata: JsonObject = Field(default_factory=dict)


class ApprovalRequest(HarnessContract):
    approval_id: ApprovalId
    run_id: RunId
    requested_action: str = Field(min_length=1)
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    policy_ids: list[str] = Field(default_factory=list)
    request_payload: JsonObject = Field(default_factory=dict)
    response_payload: JsonObject = Field(default_factory=dict)

    @field_validator("requested_at", "resolved_at")
    @classmethod
    def _approval_timestamps_must_be_timezone_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("approval timestamps must be timezone-aware")
        return value


class MemoryItem(HarnessContract):
    memory_id: MemoryId = Field(min_length=1)
    workspace_id: WorkspaceId = Field(min_length=1)
    project_id: ProjectId | None = Field(default=None, min_length=1)
    site_id: SiteId | None = Field(default=None, min_length=1)
    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_run_id: RunId | None = Field(default=None, min_length=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _memory_timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("memory timestamps must be timezone-aware")
        return value


class NormalizedGISRecord(HarnessContract):
    record_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    provider: GISProvider
    jurisdiction: str = Field(min_length=1)
    county: CountyName
    municipality: str | None = None
    normalized_type: str = Field(min_length=1)
    normalized_payload: JsonObject
    geometry: JsonObject | None = None
    centroid: JsonObject | None = None
    bbox: list[float] = Field(default_factory=list)
    spatial_reference: str | None = None
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class EvidenceItem(HarnessContract):
    evidence_id: EvidenceId
    run_id: RunId
    source_type: EvidenceSourceType
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_identifier: str | None = None
    provider: GISProvider | str
    jurisdiction: str = Field(min_length=1)
    county: CountyName | None = None
    municipality: str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    freshness_status: FreshnessStatus
    applicability: ApplicabilityStatus
    raw_excerpt: str | None = None
    normalized_text: str | None = None
    structured_payload: JsonObject = Field(default_factory=dict)
    geometry: JsonObject | None = None
    confidence: float = Field(ge=0, le=1)
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_tool_call_id: ToolCallId | None = None
    source_mode: SourceMode
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def _retrieved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value


class CalculationResult(HarnessContract):
    calculation_id: str = Field(min_length=1)
    run_id: RunId
    calculation_type: str = Field(min_length=1)
    inputs: JsonObject
    assumptions: JsonObject
    outputs: JsonObject
    formula_version: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _calculation_created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class Claim(HarnessContract):
    claim_id: ClaimId
    run_id: RunId
    report_id: ReportId
    claim_text: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    field_key: str | None = None
    kind: ClaimKind = ClaimKind.CAVEAT
    origin: ClaimOrigin = ClaimOrigin.UNKNOWN
    status: ClaimStatus
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    assumption_ids: list[AssumptionId] = Field(default_factory=list)
    transcript_segment_ids: list[TranscriptSegmentId] = Field(default_factory=list)
    training_concept_ids: list[TrainingConceptId] = Field(default_factory=list)
    source_url: str = ""
    next_verification_step: str = ""
    claim_freshness: ClaimFreshnessStatus = ClaimFreshnessStatus.UNKNOWN
    metadata: JsonObject = Field(default_factory=dict)
    source_mode: SourceMode
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _claim_created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class Report(HarnessContract):
    report_id: ReportId
    run_id: RunId
    report_type: ReportType
    title: str = Field(min_length=1)
    status: ReportStatus
    sections: list[JsonObject] = Field(default_factory=list)
    claims: list[ClaimId] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    source_mode: SourceMode
    generated_at: datetime = Field(default_factory=utc_now)
    finalized_at: datetime | None = None
    export_urls: list[str] = Field(default_factory=list)

    @field_validator("generated_at", "finalized_at")
    @classmethod
    def _report_timestamps_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("report timestamps must be timezone-aware")
        return value


class VerificationResult(HarnessContract):
    verification_id: VerificationId
    run_id: RunId
    report_id: ReportId
    status: VerificationStatus
    checks: JsonObject = Field(default_factory=dict)
    missing_evidence: list[str] = Field(default_factory=list)
    stale_evidence: list[str] = Field(default_factory=list)
    math_errors: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    jurisdiction_mismatches: list[str] = Field(default_factory=list)
    mock_or_fixture_blockers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _verification_created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value
