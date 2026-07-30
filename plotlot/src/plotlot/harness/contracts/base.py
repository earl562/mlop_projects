from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, NewType, TypeAlias

from pydantic import BaseModel, ConfigDict

WorkspaceId = NewType("WorkspaceId", str)
ProjectId = NewType("ProjectId", str)
SiteId = NewType("SiteId", str)
RunId = NewType("RunId", str)
JobId = NewType("JobId", str)
EventId = NewType("EventId", str)
SourceId = NewType("SourceId", str)
EvidenceId = NewType("EvidenceId", str)
ClaimId = NewType("ClaimId", str)
ReportId = NewType("ReportId", str)
VerificationId = NewType("VerificationId", str)
ApprovalId = NewType("ApprovalId", str)
MemoryId = NewType("MemoryId", str)
AssumptionId = NewType("AssumptionId", str)
ToolCallId = NewType("ToolCallId", str)
TranscriptId = NewType("TranscriptId", str)
TranscriptSegmentId = NewType("TranscriptSegmentId", str)
TrainingConceptId = NewType("TrainingConceptId", str)
WorkflowTemplateId = NewType("WorkflowTemplateId", str)
VideoSourceId = NewType("VideoSourceId", str)
VideoAssetId = NewType("VideoAssetId", str)
CountyName = NewType("CountyName", str)

JsonObject: TypeAlias = dict[str, Any]


class HarnessContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceMode(StrEnum):
    LIVE = "live"
    FIXTURE = "fixture"
    MOCK = "mock"
    MIXED = "mixed"


class ExecutionMode(StrEnum):
    API = "api"
    CLI = "cli"
    TUI = "tui"
    WORKER = "worker"
    LOCAL = "local"


class SourceLane(StrEnum):
    ORDINANCE_CODE = "ordinance_code"
    SOUTH_FLORIDA_GIS = "south_florida_gis"
    PARCEL_PROPERTY = "parcel_property"
    TRAINING_VIDEO = "training_video"
    USER_UPLOAD = "user_upload"
    MARKET_COMPS = "market_comps"
    COST_ASSUMPTIONS = "cost_assumptions"


class GISProvider(StrEnum):
    MIAMI_DADE_ARCGIS = "miami_dade_arcgis"
    BROWARD_GEOHUB = "broward_geohub"
    PALM_BEACH_GIS = "palm_beach_gis"
    MUNICIPAL_GIS = "municipal_gis"


class ApplicabilityScope(StrEnum):
    COUNTYWIDE = "countywide"
    MUNICIPAL = "municipal"
    UNINCORPORATED = "unincorporated"
    BMSD = "bmsd"
    PARCEL = "parcel"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


class ApplicabilityStatus(StrEnum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    NOT_APPLICABLE = "not_applicable"
    REQUIRES_MUNICIPAL_VERIFICATION = "requires_municipal_verification"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
    FIXTURE = "fixture"
    MOCK = "mock"
    REQUIRES_OFFICIAL_VERIFICATION = "requires_official_verification"


class AccessStatus(StrEnum):
    PUBLIC = "public"
    REQUIRES_KEY = "requires_key"
    REQUIRES_LOGIN = "requires_login"
    REQUIRES_PAID_SOURCE = "requires_paid_source"
    REQUIRES_USER_UPLOAD = "requires_user_upload"
    REQUIRES_USER_PROVIDED_TRANSCRIPT = "requires_user_provided_transcript"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class EvidenceSourceType(StrEnum):
    ORDINANCE_TEXT = "ordinance_text"
    MUNICODE_SECTION = "municode_section"
    GIS_LAYER = "gis_layer"
    ARCGIS_FEATURE = "arcgis_feature"
    PARCEL_RECORD = "parcel_record"
    MARKET_COMP = "market_comp"
    RENTAL_COMP = "rental_comp"
    COST_ASSUMPTION_CONFIG = "cost_assumption_config"
    ZONING_BOUNDARY = "zoning_boundary"
    ZONING_CODE_TABLE = "zoning_code_table"
    LAND_USE_LAYER = "land_use_layer"
    FLOOD_ZONE = "flood_zone"
    ENVIRONMENTAL_CONSTRAINT = "environmental_constraint"
    TRANSPORTATION_CONSTRAINT = "transportation_constraint"
    MUNICIPAL_BOUNDARY = "municipal_boundary"
    VIDEO_SOURCE = "video_source"
    CAPTION_TRACK = "caption_track"
    TRANSCRIPT_SEGMENT = "transcript_segment"
    TRAINING_CONCEPT = "training_concept"
    USER_ASSUMPTION = "user_assumption"
    CALCULATION = "calculation"


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    NEEDS_VERIFICATION = "needs_verification"
    UNSUPPORTED = "unsupported"
    PRELIMINARY = "preliminary"


class ClaimKind(StrEnum):
    VERIFIED_FACT = "verified_fact"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"
    CALCULATION = "calculation"
    TRAINING_CONCEPT = "training_concept"
    CAVEAT = "caveat"
    CONTRADICTION = "contradiction"


class ClaimOrigin(StrEnum):
    LOCAL_AUTHORITY = "local_authority"
    GIS_PROVIDER = "gis_provider"
    USER_INPUT = "user_input"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    TRAINING_CORPUS = "training_corpus"
    SYSTEM_POLICY = "system_policy"
    UNKNOWN = "unknown"


class ClaimFreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
    FIXTURE = "fixture"
    MOCK = "mock"
    REQUIRES_OFFICIAL_VERIFICATION = "requires_official_verification"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    PRELIMINARY = "preliminary"
    FINAL = "final"
    BLOCKED = "blocked"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    BLOCKED = "blocked"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MemoryType(StrEnum):
    SITE_ASSUMPTION = "site_assumption"
    PRIOR_DECISION = "prior_decision"
    VERIFIED_CONCLUSION = "verified_conclusion"
    OPEN_QUESTION = "open_question"
    JURISDICTION_FACT = "jurisdiction_fact"
    REPORT_PREFERENCE = "report_preference"
    LENDER_PREFERENCE = "lender_preference"
    USER_OVERRIDE = "user_override"
    PROJECT_BUDGET_NOTE = "project_budget_note"
    CONTRACTOR_BID_NOTE = "contractor_bid_note"
    TRAINING_WORKFLOW_PREFERENCE = "training_workflow_preference"


class ReportType(StrEnum):
    ACQUISITION_MEMO = "acquisition_memo"
    ZONING_RESEARCH_MEMO = "zoning_research_memo"
    LENDER_PACKAGE = "lender_package"
    CONSTRUCTION_BUDGET = "construction_budget"
    TRAINING_WORKFLOW = "training_workflow"
