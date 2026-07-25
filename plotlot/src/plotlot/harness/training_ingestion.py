from __future__ import annotations

import hashlib
import re

from plotlot.harness.contracts import (
    SourceMode,
    TrainingConcept,
    TrainingConceptId,
    TrainingKnowledgeUnit,
    TranscriptArtifact,
    TranscriptId,
    TranscriptSegment,
    TranscriptSegmentId,
    VideoAssetId,
    VideoSourceCatalogEntry,
    WorkflowTemplateId,
    WorkflowTemplateMapping,
)
from plotlot.harness.training_fixtures import (
    fixture_transcript_text,
    fixture_video_sources,
)


def discover_training_video_sources(
    *,
    source_mode: SourceMode,
    url: str | None = None,
    category: str | None = None,
) -> list[VideoSourceCatalogEntry]:
    videos = fixture_video_sources(source_mode)
    return [
        video
        for video in videos
        if _matches_video_filter(video, url=url, category=category)
    ]


def normalize_transcript(video: VideoSourceCatalogEntry) -> TranscriptArtifact:
    text = fixture_transcript_text(video)
    normalized = re.sub(r"\s+", " ", text).strip()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return TranscriptArtifact(
        transcript_id=TranscriptId(f"tr_{video.video_source_id}"),
        video_asset_id=VideoAssetId(f"asset_{video.video_source_id}"),
        source_type="fixture",
        raw_text=text,
        normalized_text=normalized,
        confidence=0.91,
        status="completed",
        content_hash=content_hash,
        storage_uri=f"private://training/transcripts/{content_hash}.txt",
    )


def segment_transcript(transcript: TranscriptArtifact) -> list[TranscriptSegment]:
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", transcript.normalized_text)]
    usable_chunks = [chunk for chunk in chunks if chunk]
    return [
        TranscriptSegment(
            segment_id=TranscriptSegmentId(f"seg_{transcript.transcript_id}_{index + 1:03d}"),
            transcript_id=transcript.transcript_id,
            video_asset_id=transcript.video_asset_id,
            start_seconds=index * 30,
            end_seconds=(index + 1) * 30,
            text=chunk,
            confidence=transcript.confidence,
            sequence=index + 1,
        )
        for index, chunk in enumerate(usable_chunks)
    ]


def extract_training_concepts(
    transcript: TranscriptArtifact,
    segments: list[TranscriptSegment],
) -> list[TrainingConcept]:
    text = transcript.normalized_text.casefold()
    if "arv" in text or "comparable" in text:
        return [_arv_offer_concept(transcript, segments)]
    return [_general_development_concept(transcript, segments)]


def map_concepts_to_workflow_templates(
    concepts: list[TrainingConcept],
) -> list[WorkflowTemplateMapping]:
    return [_workflow_mapping_for_concept(concept) for concept in concepts]


def build_training_knowledge_index(
    concepts: list[TrainingConcept],
) -> list[TrainingKnowledgeUnit]:
    mappings = {mapping.training_concept_id: mapping for mapping in map_concepts_to_workflow_templates(concepts)}
    return [
        TrainingKnowledgeUnit(
            knowledge_id=f"knowledge_{concept.concept_id}",
            concept_id=concept.concept_id,
            workflow_template_id=mappings[concept.concept_id].workflow_template_id,
            title=concept.title,
            description=concept.summary,
            input_fields=["subject_property", "comparable_sales", "adjustments", "offer_margin"],
            output_fields=["indicated_arv", "arv_range", "max_offer"],
            relevant_calculators=mappings[concept.concept_id].calculator_mappings,
            report_sections=mappings[concept.concept_id].report_mappings,
            risk_flags=concept.warnings,
            source_segment_ids=concept.segment_ids,
        )
        for concept in concepts
    ]


def search_training_knowledge(
    knowledge: list[TrainingKnowledgeUnit],
    *,
    keyword: str | None = None,
    calculator: str | None = None,
) -> list[TrainingKnowledgeUnit]:
    keyword_text = keyword.casefold() if keyword else None
    return [
        unit
        for unit in knowledge
        if _matches_knowledge(unit, keyword=keyword_text, calculator=calculator)
    ]


def _matches_video_filter(
    video: VideoSourceCatalogEntry,
    *,
    url: str | None,
    category: str | None,
) -> bool:
    url_matches = url is None or url in {video.page_url, video.video_url, video.embed_url}
    category_matches = category is None or video.category.casefold() == category.casefold()
    return url_matches and category_matches


def _arv_offer_concept(
    transcript: TranscriptArtifact,
    segments: list[TranscriptSegment],
) -> TrainingConcept:
    segment_ids = [segment.segment_id for segment in segments]
    return TrainingConcept(
        concept_id=TrainingConceptId("concept_arv_comps_offer"),
        transcript_id=transcript.transcript_id,
        segment_ids=segment_ids,
        category="Development Deal Analysis",
        concept_type="ARV_methodology",
        title="ARV Comparable Sales Offer Methodology",
        summary="Use adjusted comparable sales to estimate ARV and derive a max offer.",
        extracted_facts={"source_lane": "youtube_comps_arv", "calculator": "arv_comps"},
        extracted_steps=[
            "select comparable sales",
            "adjust comps to subject property",
            "estimate indicated ARV",
            "deduct costs and target profit",
            "produce max offer",
        ],
        formulas=["max_offer = indicated_arv - repair_costs - closing_costs - selling_costs - target_profit"],
        assumptions=["comps are similar enough to support ARV", "repair and sale costs are explicit"],
        warnings=["weak comps require lower confidence and independent verification"],
        confidence=0.88,
        source_attribution={
            "transcript_id": str(transcript.transcript_id),
            "segment_ids": [str(segment_id) for segment_id in segment_ids],
        },
    )


def _general_development_concept(
    transcript: TranscriptArtifact,
    segments: list[TranscriptSegment],
) -> TrainingConcept:
    segment_ids = [segment.segment_id for segment in segments]
    return TrainingConcept(
        concept_id=TrainingConceptId("concept_land_offer_workflow"),
        transcript_id=transcript.transcript_id,
        segment_ids=segment_ids,
        category="Development Deal Analysis",
        concept_type="land_valuation_methodology",
        title="Vacant Land Max Offer Workflow",
        summary="Use density, costs, rents, valuation, and residual land value for land offers.",
        extracted_facts={"source_lane": "rehabvaluator_fixture", "calculator": "residual_land_value"},
        extracted_steps=["run density study", "estimate costs", "value as built", "solve residual land value"],
        formulas=["max_land_price = stabilized_value - costs - required_profit"],
        assumptions=["cost, rent, and valuation assumptions are explicit"],
        warnings=["municipal zoning and lender assumptions require verification"],
        confidence=0.82,
        source_attribution={
            "transcript_id": str(transcript.transcript_id),
            "segment_ids": [str(segment_id) for segment_id in segment_ids],
        },
    )


def _workflow_mapping_for_concept(concept: TrainingConcept) -> WorkflowTemplateMapping:
    match concept.concept_type:
        case "ARV_methodology":
            return WorkflowTemplateMapping(
                mapping_id="mapping_arv_comps_offer",
                training_concept_id=concept.concept_id,
                workflow_template_id=WorkflowTemplateId("workflow_arv_comps_offer"),
                mapped_steps=concept.extracted_steps,
                calculator_mappings=["arv_comps"],
                report_mappings=["acquisition_memo", "evidence_appendix"],
                confidence=0.9,
            )
        case _:
            return WorkflowTemplateMapping(
                mapping_id="mapping_land_offer_workflow",
                training_concept_id=concept.concept_id,
                workflow_template_id=WorkflowTemplateId("workflow_vacant_land_max_offer"),
                mapped_steps=concept.extracted_steps,
                calculator_mappings=["density_study", "residual_land_value"],
                report_mappings=["acquisition_memo", "lender_package"],
                confidence=0.84,
            )


def _matches_knowledge(
    unit: TrainingKnowledgeUnit,
    *,
    keyword: str | None,
    calculator: str | None,
) -> bool:
    text = f"{unit.title} {unit.description}".casefold()
    keyword_matches = keyword is None or keyword in text
    calculator_matches = calculator is None or calculator in unit.relevant_calculators
    return keyword_matches and calculator_matches
