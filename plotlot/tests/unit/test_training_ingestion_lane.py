from __future__ import annotations

from plotlot.harness.contracts import SourceMode
from plotlot.harness.training_ingestion import (
    build_training_knowledge_index,
    discover_training_video_sources,
    extract_training_concepts,
    map_concepts_to_workflow_templates,
    normalize_transcript,
    search_training_knowledge,
    segment_transcript,
)


def test_youtube_arv_source_is_classified_into_offer_analysis_workflow() -> None:
    # Given: the supplied public YouTube ARV/comps source URL.
    url = "https://www.youtube.com/watch?v=0IS1iFMJ8sQ"

    # When: the fixture discovery lane registers it.
    videos = discover_training_video_sources(source_mode=SourceMode.FIXTURE, url=url)

    # Then: the source is categorized for comps, ARV, and acquisition underwriting.
    assert len(videos) == 1
    video = videos[0]
    assert video.platform_video_id == "0IS1iFMJ8sQ"
    assert "sales comps" in video.metadata["tags"]
    assert "ARV" in video.metadata["tags"]
    assert "offer analysis" in video.metadata["tags"]
    assert video.access_status == "public"


def test_transcript_segments_keep_timestamps_and_source_ids() -> None:
    # Given: fixture transcript text from the ARV/comps lane.
    video = discover_training_video_sources(
        source_mode=SourceMode.FIXTURE,
        url="https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
    )[0]
    transcript = normalize_transcript(video)

    # When: the transcript is segmented.
    segments = segment_transcript(transcript)

    # Then: segments are attributable back to the private transcript artifact.
    assert segments
    assert segments[0].transcript_id == transcript.transcript_id
    assert segments[0].video_asset_id == transcript.video_asset_id
    assert segments[0].start_seconds == 0
    assert segments[0].end_seconds > segments[0].start_seconds


def test_training_extraction_maps_concepts_to_workflow_templates() -> None:
    # Given: a fixture ARV/comps transcript and segments.
    video = discover_training_video_sources(
        source_mode=SourceMode.FIXTURE,
        url="https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
    )[0]
    transcript = normalize_transcript(video)
    segments = segment_transcript(transcript)

    # When: concepts are extracted and mapped to reusable workflows.
    concepts = extract_training_concepts(transcript, segments)
    mappings = map_concepts_to_workflow_templates(concepts)

    # Then: extraction is structured, attributable, and workflow-linked.
    assert concepts
    assert concepts[0].segment_ids
    assert concepts[0].concept_type == "ARV_methodology"
    assert any(mapping.workflow_template_id == "workflow_arv_comps_offer" for mapping in mappings)


def test_training_knowledge_search_filters_by_calculator_and_keyword() -> None:
    # Given: extracted training knowledge from the fixture YouTube source.
    video = discover_training_video_sources(
        source_mode=SourceMode.FIXTURE,
        url="https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
    )[0]
    transcript = normalize_transcript(video)
    segments = segment_transcript(transcript)
    concepts = extract_training_concepts(transcript, segments)
    knowledge = build_training_knowledge_index(concepts)

    # When: an analyst searches for offer-related ARV knowledge.
    results = search_training_knowledge(knowledge, keyword="offer", calculator="arv_comps")

    # Then: the result links to concept and transcript segment IDs instead of a blob summary.
    assert results
    assert results[0].concept_id == concepts[0].concept_id
    assert results[0].source_segment_ids == concepts[0].segment_ids
