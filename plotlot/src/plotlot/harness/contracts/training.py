from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from plotlot.harness.contracts.base import (
    AccessStatus,
    HarnessContract,
    JsonObject,
    SourceMode,
    TrainingConceptId,
    TranscriptId,
    TranscriptSegmentId,
    VideoAssetId,
    VideoSourceId,
    WorkflowTemplateId,
    utc_now,
)


class VideoSourceCatalogEntry(HarnessContract):
    video_source_id: VideoSourceId
    provider: str = Field(min_length=1)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    page_url: str = Field(min_length=1)
    video_url: str | None = None
    embed_url: str | None = None
    platform_video_id: str | None = None
    source_page_url: str | None = None
    access_status: AccessStatus
    discovered_at: datetime = Field(default_factory=utc_now)
    last_checked_at: datetime = Field(default_factory=utc_now)
    metadata: JsonObject = Field(default_factory=dict)
    source_mode: SourceMode

    @field_validator("discovered_at", "last_checked_at")
    @classmethod
    def _timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("video source timestamps must be timezone-aware")
        return value


class TranscriptArtifact(HarnessContract):
    transcript_id: TranscriptId
    video_asset_id: VideoAssetId
    source_type: str = Field(min_length=1)
    language: str = "en"
    raw_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    segment_count: int = Field(default=0, ge=0)
    retrieved_at: datetime = Field(default_factory=utc_now)
    generated_at: datetime | None = None
    transcription_provider: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    storage_uri: str | None = None


class TranscriptSegment(HarnessContract):
    segment_id: TranscriptSegmentId
    transcript_id: TranscriptId
    video_asset_id: VideoAssetId
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=0)
    text: str = Field(min_length=1)
    speaker: str | None = None
    confidence: float = Field(ge=0, le=1)
    sequence: int = Field(ge=1)
    embedding_id: str | None = None


class TrainingConcept(HarnessContract):
    concept_id: TrainingConceptId
    transcript_id: TranscriptId
    segment_ids: list[TranscriptSegmentId] = Field(min_length=1)
    category: str = Field(min_length=1)
    concept_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    extracted_facts: JsonObject
    extracted_steps: list[str]
    formulas: list[str]
    assumptions: list[str]
    warnings: list[str]
    confidence: float = Field(ge=0, le=1)
    source_attribution: JsonObject


class WorkflowTemplateMapping(HarnessContract):
    mapping_id: str = Field(min_length=1)
    training_concept_id: TrainingConceptId
    workflow_template_id: WorkflowTemplateId
    mapped_steps: list[str]
    calculator_mappings: list[str]
    report_mappings: list[str]
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)


class TrainingKnowledgeUnit(HarnessContract):
    knowledge_id: str = Field(min_length=1)
    concept_id: TrainingConceptId
    workflow_template_id: WorkflowTemplateId
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_fields: list[str]
    output_fields: list[str]
    relevant_calculators: list[str]
    report_sections: list[str]
    risk_flags: list[str]
    source_segment_ids: list[TranscriptSegmentId]
    created_at: datetime = Field(default_factory=utc_now)
