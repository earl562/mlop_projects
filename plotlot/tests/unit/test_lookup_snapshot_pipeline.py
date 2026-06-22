from __future__ import annotations


def test_report_to_dict_includes_lookup_snapshot_fields() -> None:
    from plotlot.core.lookup_snapshot import FieldKey
    from plotlot.core.types import PropertyRecord, SearchResult
    from plotlot.pipeline.lookup import _build_fallback_report, report_to_dict

    # Given
    report = _build_fallback_report(
        "7940 Plantation Blvd, Miramar, FL 33023",
        {
            "formatted_address": "7940 Plantation Blvd, Miramar, FL 33023",
            "municipality": "Miramar",
            "county": "Broward",
            "lat": 25.977,
            "lng": -80.232,
        },
        PropertyRecord(
            folio="504210230010",
            address="7940 PLANTATION BLVD",
            municipality="Miramar",
            county="Broward",
            zoning_code="RS-4",
            lot_size_sqft=8000.0,
        ),
        ["Sec. 500"],
        [
            SearchResult(
                section="Sec. 500",
                section_title="Dimensional Standards",
                zone_codes=["RS-4"],
                chunk_text="Maximum height is 35 feet. Parking is 2 spaces per unit.",
                score=0.91,
                municipality="Miramar",
                chunk_id=42,
            )
        ],
    )

    # When
    payload = report_to_dict(report)
    snapshot = payload["lookup_snapshot"]
    fields = {field["key"]: field for field in snapshot["fields"]}

    # Then
    assert FieldKey("parcel.apn") in fields
    assert FieldKey("zoning.district") in fields
    assert fields[FieldKey("parcel.apn")]["display_state"] == "verified"
    assert fields[FieldKey("zoning.district")]["evidence_ids"]


def test_parcel_only_evidence_does_not_verify_zoning_or_calculations() -> None:
    from plotlot.core.lookup_snapshot import DisplayState, FieldKey
    from plotlot.core.types import DensityAnalysis, PropertyRecord, ZoningReport
    from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot

    # Given
    report = ZoningReport(
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
        sources=["official assessor parcel record"],
        density_analysis=DensityAnalysis(
            max_units=2,
            governing_constraint="density",
            constraints=[],
            lot_size_sqft=8000.0,
            confidence="medium",
        ),
        confidence="medium",
    )

    # When
    snapshot = build_lookup_snapshot(report)
    fields = {field.key: field for field in snapshot.fields}

    # Then
    assert fields[FieldKey("parcel.apn")].display_state == DisplayState.VERIFIED
    assert fields[FieldKey("zoning.district")].display_state == DisplayState.UNKNOWN
    assert fields[FieldKey("zoning.district")].evidence_ids == ()
    assert fields[FieldKey("standards.height")].display_state == DisplayState.UNKNOWN
    assert fields[FieldKey("standards.height")].evidence_ids == ()
    assert fields[FieldKey("calc.max_units")].display_state == DisplayState.UNKNOWN
    assert fields[FieldKey("calc.max_units")].evidence_ids == ()
    assert fields[FieldKey("confidence")].display_state == DisplayState.UNKNOWN
    assert snapshot.calculations[0].input_evidence_ids == ()
    assert not snapshot.calculations[0].is_reproducible


def test_conflicting_parcel_and_ordinance_zoning_marks_field_contradicted() -> None:
    from plotlot.core.lookup_snapshot import DisplayState, FieldKey
    from plotlot.core.types import PropertyRecord, SourceRef, ZoningReport
    from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot

    # Given
    report = ZoningReport(
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
            zoning_code="RM-2",
            lot_size_sqft=8000.0,
        ),
        source_refs=(
            SourceRef(
                section="Sec. 500",
                section_title="Dimensional Standards",
                chunk_text_preview="RS-4 height and parking standards.",
                score=0.91,
            ),
        ),
        sources=["https://example.test/ordinance/sec-500"],
        confidence="medium",
    )

    # When
    snapshot = build_lookup_snapshot(report)
    fields = {field.key: field for field in snapshot.fields}
    zoning_field = fields[FieldKey("zoning.district")]

    # Then
    assert zoning_field.display_state == DisplayState.CONTRADICTED
    assert zoning_field.confidence == 0.0
    assert not zoning_field.is_display_ready
    assert len(zoning_field.evidence_ids) == 2
    assert "contradictory_sources" in zoning_field.warnings


def test_api_response_preserves_lookup_snapshot() -> None:
    from dataclasses import asdict

    from plotlot.api.schemas import ZoningReportResponse
    from plotlot.core.types import PropertyRecord, ZoningReport
    from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot

    # Given
    report = ZoningReport(
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
        sources=["Sec. 500"],
        confidence="medium",
    )
    report.lookup_snapshot = build_lookup_snapshot(report)

    # When
    response = ZoningReportResponse(**asdict(report))

    # Then
    assert response.lookup_snapshot is not None
    assert response.lookup_snapshot.fields[0].evidence_ids
