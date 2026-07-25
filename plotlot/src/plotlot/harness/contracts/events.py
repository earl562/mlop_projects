from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from plotlot.harness.contracts.base import (
    EventId,
    ExecutionMode,
    HarnessContract,
    JsonObject,
    ProjectId,
    RunId,
    SiteId,
    SourceMode,
    WorkspaceId,
    utc_now,
)


class PlotLotEventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    RUN_COMPLETED = "run.completed"
    JOB_CREATED = "job.created"
    JOB_QUEUED = "job.queued"
    JOB_STARTED = "job.started"
    JOB_RETRY_SCHEDULED = "job.retry_scheduled"
    JOB_COMPLETED = "job.completed"
    JOB_CANCELLED = "job.cancelled"
    JOB_FAILED = "job.failed"
    JOB_DEAD_LETTERED = "job.dead_lettered"
    SKILL_SELECTED = "skill.selected"
    TOOL_REQUESTED = "tool.requested"
    TOOL_POLICY_CHECKED = "tool.policy_checked"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_DENIED = "tool.denied"
    TOOL_APPROVAL_REQUIRED = "tool.approval_required"
    EVIDENCE_CREATED = "evidence.created"
    EVIDENCE_LINKED_TO_CLAIM = "evidence.linked_to_claim"
    CALCULATION_STARTED = "calculation.started"
    CALCULATION_COMPLETED = "calculation.completed"
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_COMPLETED = "verification.completed"
    REPORT_GENERATED = "report.generated"
    REPORT_EXPORTED = "report.exported"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    APPROVAL_EXPIRED = "approval.expired"
    GIS_SOURCE_CATALOG_LOADED = "gis.source_catalog.loaded"
    GIS_FEATURE_QUERY_COMPLETED = "gis.feature_query.completed"
    GIS_EVIDENCE_CREATED = "gis.evidence.created"
    GIS_APPLICABILITY_CLASSIFIED = "gis.applicability.classified"
    VIDEO_DISCOVERY_COMPLETED = "video.discovery.completed"
    TRANSCRIPT_SEGMENTED = "transcript.segmented"
    TRAINING_CONCEPT_EXTRACTED = "training.concept.extracted"
    TRAINING_WORKFLOW_MAPPED = "training.workflow.mapped"
    CODEX_GOAL_GENERATED = "codex.goal.generated"
    SCAFFOLD_STARTED = "scaffold.started"
    SCAFFOLD_FILE_CREATED = "scaffold.file_created"
    SCAFFOLD_FILE_SKIPPED = "scaffold.file_skipped"
    SCAFFOLD_COMPLETED = "scaffold.completed"
    SCAFFOLD_FAILED = "scaffold.failed"


class PlotLotEventSource(StrEnum):
    HARNESS = "harness"
    TOOL = "tool"
    POLICY = "policy"
    VERIFIER = "verifier"
    REPORT = "report"
    FRONTEND = "frontend"
    CLI = "cli"
    TUI = "tui"
    WORKER = "worker"
    SYSTEM = "system"


class PlotLotEventStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PlotLotEventError(HarnessContract):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: JsonObject | None = None


class PlotLotEvent(HarnessContract):
    run_id: RunId
    sequence: int = Field(ge=1)
    type: PlotLotEventType
    payload: JsonObject
    source: PlotLotEventSource
    event_id: EventId | None = None
    workspace_id: WorkspaceId | None = None
    project_id: ProjectId | None = None
    site_id: SiteId | None = None
    status: PlotLotEventStatus | None = None
    source_mode: SourceMode | None = None
    execution_mode: ExecutionMode | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    parent_event_id: EventId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    error: PlotLotEventError | None = None

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value
