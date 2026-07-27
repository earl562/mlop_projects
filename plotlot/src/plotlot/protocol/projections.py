from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.protocol.base import ProtocolModel


ProcessingStatus = Literal["queued", "running", "complete", "blocked", "cancelled", "failed"]
ReadinessStatus = Literal["blocked", "provisional", "ready"]
PricingStatus = Literal["unpriced", "provisional", "evidence-supported"]
ReviewStatus = Literal["unreviewed", "review-required", "approved", "changes-requested"]
ReleaseStatus = Literal["blocked", "eligible", "released", "revoked"]


class OpportunityAcceptedV1(ProtocolModel):
    schema_version: Literal["OpportunityAcceptedV1"]
    host_analysis_id: str = Field(pattern=r"^analysis_[A-Za-z0-9_-]+$")
    host_run_id: str = Field(pattern=r"^hostrun_[A-Za-z0-9_-]+$")
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    revision_number: int = Field(ge=1)
    processing_status: ProcessingStatus
    reused: bool
    retry_after_seconds: int | None = Field(default=None, ge=1)
    event_cursor: str = Field(pattern=r"^evtcur_[A-Za-z0-9_-]+$")


class EngineRunProjectionV1(ProtocolModel):
    schema_version: Literal["EngineRunProjectionV1"]
    tenant_id: str = Field(pattern=r"^tenant_[A-Za-z0-9_-]+$")
    host_analysis_id: str = Field(pattern=r"^analysis_[A-Za-z0-9_-]+$")
    host_run_id: str = Field(pattern=r"^hostrun_[A-Za-z0-9_-]+$")
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    current_engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    current_revision_number: int = Field(ge=1)
    processing_status: ProcessingStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deadline_at: AwareDatetime
    terminal: bool


class EngineRevisionProjectionV1(ProtocolModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "type": "object",
                        "properties": {"release_status": {"const": "released"}},
                        "required": ["release_status"],
                    },
                    "then": {
                        "type": "object",
                        "properties": {
                            "processing_status": {"const": "complete"},
                            "readiness_status": {"const": "ready"},
                            "pricing_status": {"const": "evidence-supported"},
                            "review_status": {"const": "approved"},
                            "evidence_ids": {"minItems": 1},
                            "blocker_codes": {"maxItems": 0},
                        },
                    },
                },
            ],
        },
    )

    schema_version: Literal["EngineRevisionProjectionV1"]
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    revision_number: int = Field(ge=1)
    parent_engine_revision_id: str | None = Field(
        default=None,
        pattern=r"^engrev_[A-Za-z0-9_-]+$",
    )
    processing_status: ProcessingStatus
    readiness_status: ReadinessStatus
    pricing_status: PricingStatus
    review_status: ReviewStatus
    release_status: ReleaseStatus
    evidence_ids: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime

    @model_validator(mode="after")
    def release_does_not_widen_dimensions(self) -> Self:
        if self.release_status == "released" and (
            self.processing_status != "complete"
            or self.readiness_status != "ready"
            or self.pricing_status != "evidence-supported"
            or self.review_status != "approved"
            or not self.evidence_ids
            or self.blocker_codes
        ):
            raise PydanticCustomError(
                "protocol_status_widening",
                "released revision must be complete, ready, priced, approved, and evidenced",
            )
        return self


class EngineEventProjectionV1(ProtocolModel):
    schema_version: Literal["EngineEventProjectionV1"]
    event_id: str = Field(pattern=r"^event_[A-Za-z0-9_-]+$")
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    sequence: int = Field(ge=1)
    cursor: str = Field(pattern=r"^evtcur_[A-Za-z0-9_-]+$")
    event_type: Literal[
        "run-accepted",
        "stage-started",
        "evidence-recorded",
        "revision-completed",
        "run-blocked",
        "run-cancelled",
        "run-failed",
        "run-replayed",
    ]
    occurred_at: AwareDatetime
    causation_event_id: str | None = Field(default=None, pattern=r"^event_[A-Za-z0-9_-]+$")
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceProjectionV1(ProtocolModel):
    schema_version: Literal["EvidenceProjectionV1"]
    evidence_id: str = Field(pattern=r"^evidence_[A-Za-z0-9_-]+$")
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    claim_key: str = Field(min_length=1)
    support_status: Literal["accepted", "ambiguous", "stale", "conflict", "unsupported"]
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: AwareDatetime
    effective_at: AwareDatetime | None = None
    replay_uri: str = Field(min_length=1)


class ReportProjectionV1(ProtocolModel):
    schema_version: Literal["ReportProjectionV1"]
    report_id: str = Field(pattern=r"^report_[A-Za-z0-9_-]+$")
    host_run_id: str = Field(pattern=r"^hostrun_[A-Za-z0-9_-]+$")
    engine_run_id: str = Field(pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str = Field(pattern=r"^engrev_[A-Za-z0-9_-]+$")
    processing_status: ProcessingStatus
    readiness_status: ReadinessStatus
    pricing_status: PricingStatus
    review_status: ReviewStatus
    release_status: ReleaseStatus
    evidence_ids: tuple[str, ...]
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime


class EventPageV1(ProtocolModel):
    schema_version: Literal["EventPageV1"]
    items: tuple[EngineEventProjectionV1, ...]
    next_cursor: str | None = Field(default=None, pattern=r"^evtcur_[A-Za-z0-9_-]+$")


class EvidencePageV1(ProtocolModel):
    schema_version: Literal["EvidencePageV1"]
    items: tuple[EvidenceProjectionV1, ...]
    next_cursor: str | None = Field(default=None, pattern=r"^evcur_[A-Za-z0-9_-]+$")
