from __future__ import annotations


def test_verified_field_when_evidence_and_quality_pass() -> None:
    from plotlot.core.lookup_snapshot import (
        ContradictionStatus,
        DisplayState,
        EvidenceId,
        FailureBehavior,
        FieldKey,
        FieldQuality,
        FreshnessStatus,
        LookupField,
        LookupFieldSpec,
    )

    # Given
    spec = LookupFieldSpec(
        key=FieldKey("zoning.district"),
        label="Zoning district",
        value="RS-4",
        unit="",
        evidence_ids=(EvidenceId("ev_zoning_miramar_abc123_20260621"),),
        source_priority=("official_zoning_map",),
        fallback_sources=("official_parcel_record",),
        failure_behavior=FailureBehavior.UNKNOWN,
    )
    quality = FieldQuality(
        accepted_authority=True,
        freshness=FreshnessStatus.CURRENT,
        units_normalized=True,
        parser_confidence=0.94,
        contradiction_status=ContradictionStatus.CLEAR,
    )

    # When
    field = LookupField.from_quality(spec, quality)

    # Then
    assert field.display_state is DisplayState.VERIFIED
    assert field.confidence == 0.94
    assert field.is_display_ready
    assert field.evidence_ids == (EvidenceId("ev_zoning_miramar_abc123_20260621"),)


def test_unknown_field_when_evidence_is_missing() -> None:
    from plotlot.core.lookup_snapshot import (
        ContradictionStatus,
        DisplayState,
        FailureBehavior,
        FieldKey,
        FieldQuality,
        FreshnessStatus,
        LookupField,
        LookupFieldSpec,
    )

    # Given
    spec = LookupFieldSpec(
        key=FieldKey("standards.height"),
        label="Maximum height",
        value="",
        unit="ft",
        evidence_ids=(),
        source_priority=("official_ordinance_table",),
        fallback_sources=("adopted_planning_pdf",),
        failure_behavior=FailureBehavior.UNKNOWN,
    )
    quality = FieldQuality(
        accepted_authority=True,
        freshness=FreshnessStatus.CURRENT,
        units_normalized=True,
        parser_confidence=0.91,
        contradiction_status=ContradictionStatus.CLEAR,
    )

    # When
    field = LookupField.from_quality(spec, quality)

    # Then
    assert field.display_state is DisplayState.UNKNOWN
    assert not field.is_display_ready
    assert field.evidence_ids == ()
    assert field.warnings == ("missing_evidence",)


def test_contradiction_blocks_display_ready_field() -> None:
    from plotlot.core.lookup_snapshot import (
        ContradictionStatus,
        DisplayState,
        EvidenceId,
        FailureBehavior,
        FieldKey,
        FieldQuality,
        FreshnessStatus,
        LookupField,
        LookupFieldSpec,
    )

    # Given
    spec = LookupFieldSpec(
        key=FieldKey("zoning.district"),
        label="Zoning district",
        value="RS-4",
        unit="",
        evidence_ids=(
            EvidenceId("ev_zoning_map_miramar_abc123_20260621"),
            EvidenceId("ev_parcel_record_miramar_def456_20260621"),
        ),
        source_priority=("official_zoning_map",),
        fallback_sources=("official_parcel_record",),
        failure_behavior=FailureBehavior.ESCALATE,
    )
    quality = FieldQuality(
        accepted_authority=True,
        freshness=FreshnessStatus.CURRENT,
        units_normalized=True,
        parser_confidence=0.98,
        contradiction_status=ContradictionStatus.BLOCKING,
    )

    # When
    field = LookupField.from_quality(spec, quality)

    # Then
    assert field.display_state is DisplayState.CONTRADICTED
    assert field.confidence == 0.0
    assert not field.is_display_ready


def test_calculation_trace_is_reproducible_only_with_input_evidence() -> None:
    from plotlot.core.lookup_snapshot import CalculationTrace, EvidenceId

    # Given
    sourced_trace = CalculationTrace(
        calculator_name="max_units",
        calculator_version="2026.06.21",
        formula="lot_area_sqft / min_lot_area_per_unit_sqft",
        input_evidence_ids=(EvidenceId("ev_parcel_area_miramar_abc123_20260621"),),
        output_label="max_units=1",
        warnings=(),
    )
    unsourced_trace = CalculationTrace(
        calculator_name="max_units",
        calculator_version="2026.06.21",
        formula="lot_area_sqft / min_lot_area_per_unit_sqft",
        input_evidence_ids=(),
        output_label="max_units=1",
        warnings=("missing_density_evidence",),
    )

    # When
    sourced_reproducible = sourced_trace.is_reproducible
    unsourced_reproducible = unsourced_trace.is_reproducible

    # Then
    assert sourced_reproducible
    assert not unsourced_reproducible


def test_lookup_snapshot_returns_field_evidence_ids() -> None:
    from plotlot.core.lookup_snapshot import (
        ContradictionStatus,
        EvidenceId,
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

    # Given
    field_key = FieldKey("parcel.apn")
    evidence_id = EvidenceId("ev_parcel_miramar_abc123_20260621")
    field = LookupField.from_quality(
        LookupFieldSpec(
            key=field_key,
            label="APN",
            value="504210230010",
            unit="",
            evidence_ids=(evidence_id,),
            source_priority=("official_assessor",),
            fallback_sources=("parcel_gis_layer",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=1.0,
            contradiction_status=ContradictionStatus.CLEAR,
        ),
    )
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_test"),
        site_id=SiteId("site_test"),
        run_id=RunId("run_test"),
        fields=(field,),
        calculations=(),
        warnings=(),
    )

    # When
    evidence_ids = snapshot.evidence_ids_for(field_key)
    missing_evidence_ids = snapshot.evidence_ids_for(FieldKey("zoning.district"))

    # Then
    assert evidence_ids == (evidence_id,)
    assert missing_evidence_ids == ()
