from __future__ import annotations

from plotlot.core.lookup_snapshot import (
    ContradictionStatus,
    DisplayState,
    EvidenceId,
    EvidenceSourceMetadata,
    FieldKey,
    FieldQuality,
    FreshnessStatus,
    LookupField,
    LookupFieldSpec,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.harness import ContextBroker, ContextBuildRequest
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_fields import zoning_field
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_context_broker_builds_lookup_snapshot_context_packet() -> None:
    # Given: a verified lookup snapshot with recorded evidence and calculation trace.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    request = ContextBuildRequest(
        workspace_id="ws_test",
        project_id="project_test",
        site_id=str(snapshot.site_id),
        objective="Find by-right development capacity.",
        lookup_snapshot=snapshot,
    )

    # When: the context broker prepares the packet for an agent/tool turn.
    packet = ContextBroker().build_packet(request)

    # Then: the packet carries source-backed facts and reproducible calculator context.
    max_units = [field for field in packet.fields if field.key == FieldKey("calc.max_units")]
    assert len(max_units) == 1
    assert max_units[0].display_state is DisplayState.VERIFIED
    assert max_units[0].evidence_ids == packet.evidence_ids
    assert packet.calculations[0].calculator_name == "max_units"
    assert packet.calculations[0].input_evidence_ids == packet.evidence_ids
    assert packet.calculations[0].is_reproducible is True
    assert {item.evidence_id for item in packet.evidence_packets} == set(packet.evidence_ids)
    assert all(item.referenced_field_keys for item in packet.evidence_packets)
    assert {item.source_authority for item in packet.evidence_packets} == {
        "official_assessor",
        "official_zoning_ordinance",
    }
    assert all(item.quality_score == 0.0 for item in packet.evidence_packets)
    assert all("missing_source_url" in item.quality_flags for item in packet.evidence_packets)
    assert all("missing_effective_date" in item.quality_flags for item in packet.evidence_packets)
    assert all(item.lineage for item in packet.evidence_packets)


def test_context_broker_marks_unresolved_lookup_fields_as_open_questions() -> None:
    # Given: a snapshot with unknown and contradicted fields that must not be trusted silently.
    unknown = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("standards.height"),
            label="Maximum height",
            value=None,
            unit="ft",
            evidence_ids=(),
            source_priority=("official_ordinance_table",),
            fallback_sources=("adopted_planning_pdf",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.95,
            contradiction_status=ContradictionStatus.CLEAR,
        ),
    )
    contradicted = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("zoning.district"),
            label="Zoning district",
            value="RM-2",
            unit="",
            evidence_ids=(EvidenceId("ev_map"), EvidenceId("ev_parcel")),
            source_priority=("official_zoning_map",),
            fallback_sources=("official_parcel_record",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.99,
            contradiction_status=ContradictionStatus.BLOCKING,
        ),
    )
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_context_test"),
        site_id=SiteId("site_context_test"),
        run_id=RunId("run_context_test"),
        fields=(unknown, contradicted),
        calculations=(),
        warnings=("snapshot_warning",),
    )

    # When: the broker builds agent context from unresolved lookup evidence.
    packet = ContextBroker().build_packet(
        ContextBuildRequest(
            workspace_id="ws_test",
            objective="Assess zoning capacity.",
            lookup_snapshot=snapshot,
        )
    )

    # Then: unresolved fields remain visible as warnings/open questions, not facts.
    assert packet.fields[0].display_state is DisplayState.UNKNOWN
    assert packet.fields[1].display_state is DisplayState.CONTRADICTED
    assert "snapshot_warning" in packet.warnings
    assert "missing_evidence" in packet.warnings
    assert any("standards.height is unknown" in question for question in packet.open_questions)
    assert any("zoning.district is contradicted" in question for question in packet.open_questions)


def test_context_broker_escalates_stale_source_quality_flags() -> None:
    # Given: a verified-looking field is backed by stale official ordinance evidence.
    evidence_id = EvidenceId("ev_ordinance_stale")
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_context_stale_source"),
        site_id=SiteId("site_context_stale_source"),
        run_id=RunId("run_context_stale_source"),
        fields=(
            zoning_field(
                "zoning.district",
                "Zoning district",
                "RS-4",
                "",
                (evidence_id,),
            ),
        ),
        calculations=(),
        warnings=(),
        source_metadata=(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url="https://example.gov/zoning-code",
                source_title="Zoning Code",
                effective_date="2020-01-01",
            ),
        ),
    )

    # When: the broker prepares runtime context for the agent.
    packet = ContextBroker().build_packet(
        ContextBuildRequest(
            workspace_id="ws_test",
            objective="Assess zoning capacity.",
            lookup_snapshot=snapshot,
        )
    )

    # Then: stale evidence becomes a warning and an open verification question.
    assert packet.evidence_packets[0].quality_flags == ("stale_source",)
    assert "stale_source" in packet.warnings
    assert any(
        "ev_ordinance_stale is stale" in question and "zoning.district" in question
        for question in packet.open_questions
    )


def test_context_broker_carries_explicit_source_metadata_packets() -> None:
    # Given: a lookup snapshot source has explicit authority and parser lineage.
    evidence_id = EvidenceId("ev_custom_zoning_layer")
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_context_explicit_source"),
        site_id=SiteId("site_context_explicit_source"),
        run_id=RunId("run_context_explicit_source"),
        fields=(
            zoning_field(
                "zoning.district",
                "Zoning district",
                "RS-4",
                "",
                (evidence_id,),
            ),
        ),
        calculations=(),
        warnings=(),
        source_metadata=(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url="https://example.gov/arcgis/rest/services/Zoning/MapServer/0",
                source_title="Official Zoning Layer",
                source_type="authoritative_public_record",
                source_authority="official_gis",
                publisher="City GIS Department",
                retrieved_at="2026-06-21T10:15:00+00:00",
                effective_date="2026-01-15",
                parser_version="arcgis_feature.v2",
                schema_version="zoning_layer.v4",
                raw_artifact_ref="sha256:raw-zoning-feature",
                query_parameters=("f=json", "where=1=1"),
            ),
        ),
    )

    # When: the broker builds agent context from the lookup snapshot.
    packet = ContextBroker().build_packet(
        ContextBuildRequest(
            workspace_id="ws_test",
            objective="Assess zoning capacity.",
            lookup_snapshot=snapshot,
        )
    )

    # Then: the evidence packet keeps the source provenance needed by agent traces.
    evidence_packet = packet.evidence_packets[0]
    assert evidence_packet.source_type == "authoritative_public_record"
    assert evidence_packet.source_authority == "official_gis"
    assert evidence_packet.publisher == "City GIS Department"
    assert evidence_packet.retrieved_at == "2026-06-21T10:15:00+00:00"
    assert evidence_packet.parser_version == "arcgis_feature.v2"
    assert evidence_packet.schema_version == "zoning_layer.v4"
    assert evidence_packet.raw_artifact_ref == "sha256:raw-zoning-feature"
    assert evidence_packet.query_parameters == ("f=json", "where=1=1")
