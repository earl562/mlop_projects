from __future__ import annotations

from dataclasses import replace

from plotlot.core.lookup_snapshot import EvidenceSourceMetadata
from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_serialization import (
    lookup_snapshot_from_dict,
    lookup_snapshot_to_dict,
)


def test_lookup_snapshot_round_trips_through_json_payload() -> None:
    # Given: a typed lookup snapshot with parcel and ordinance evidence.
    snapshot = build_lookup_snapshot(
        ZoningReport(
            address="7940 Plantation Blvd, Miramar, FL 33023",
            formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
            municipality="Miramar",
            county="Broward",
            zoning_district="RS-4",
            max_height="35 ft",
            property_record=PropertyRecord(
                folio="504210230010",
                address="7940 PLANTATION BLVD",
                municipality="Miramar",
                county="Broward",
                zoning_code="RS-4",
                lot_size_sqft=8000.0,
            ),
            source_refs=[
                SourceRef(
                    section="Sec. 500",
                    section_title="Dimensional Standards",
                    chunk_text_preview="RS-4 height and parking standards.",
                    score=0.91,
                )
            ],
            confidence="medium",
        )
    )

    # When: the snapshot is serialized and parsed from the stored JSON shape.
    restored = lookup_snapshot_from_dict(lookup_snapshot_to_dict(snapshot))

    # Then: all fields, evidence IDs, display states, and warnings are preserved.
    assert restored == snapshot


def test_lookup_snapshot_source_metadata_round_trips_authority_lineage() -> None:
    # Given: source metadata carries explicit authority and ingestion lineage.
    snapshot = build_lookup_snapshot(
        ZoningReport(
            address="7940 Plantation Blvd, Miramar, FL 33023",
            formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
            municipality="Miramar",
            county="Broward",
            zoning_district="RS-4",
            property_record=PropertyRecord(
                folio="504210230010",
                address="7940 PLANTATION BLVD",
                municipality="Miramar",
                county="Broward",
                zoning_code="RS-4",
                lot_size_sqft=8000.0,
            ),
            source_refs=[
                SourceRef(
                    section="Sec. 500",
                    section_title="Dimensional Standards",
                    chunk_text_preview="RS-4 height and parking standards.",
                    score=0.91,
                )
            ],
            confidence="medium",
        )
    )
    evidence_id = snapshot.source_metadata[0].evidence_id
    snapshot = replace(
        snapshot,
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

    # When: the snapshot is serialized and restored from JSON.
    restored = lookup_snapshot_from_dict(lookup_snapshot_to_dict(snapshot))

    # Then: authority, publisher, query, and parser lineage are preserved.
    assert restored == snapshot
