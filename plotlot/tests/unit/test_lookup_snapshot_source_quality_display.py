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
from plotlot.pipeline.lookup_snapshot_store import build_stored_lookup_snapshot


def test_user_uploaded_evidence_requires_review_before_display() -> None:
    # Given: a field is initially verified but only backed by a user-uploaded source.
    evidence_id = EvidenceId("ev_upload_zoning_letter")
    field = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("zoning.district"),
            label="Zoning district",
            value="RS-4",
            unit="",
            evidence_ids=(evidence_id,),
            source_priority=("official_zoning_map",),
            fallback_sources=("user_uploaded_document",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.95,
            contradiction_status=ContradictionStatus.CLEAR,
        ),
    )
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_upload_candidate"),
        site_id=SiteId("site_upload_candidate"),
        run_id=RunId("run_upload_candidate"),
        fields=(field,),
        calculations=(),
        warnings=(),
        source_metadata=(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url="https://storage.example.test/user/zoning-letter.pdf",
                source_title="Uploaded zoning letter",
                source_type="user_uploaded_document",
                source_authority="user_upload",
                publisher="user_upload",
                retrieved_at="2026-06-01T00:00:00+00:00",
                effective_date="2026-01-01",
                parser_version="upload_pdf.v1",
                schema_version="lookup_snapshot_record.v1",
                raw_artifact_ref="uploads/zoning-letter.pdf",
            ),
        ),
    )

    # When: source quality is applied while storing the lookup snapshot.
    stored = build_stored_lookup_snapshot(snapshot)
    stored_field = stored.snapshot.fields[0]

    # Then: the field is not display-ready until an authoritative source verifies it.
    assert stored_field.display_state is DisplayState.REQUIRES_HUMAN_REVIEW
    assert not stored_field.is_display_ready
    assert stored_field.confidence == 0.4
    assert stored_field.warnings == ("user_uploaded_document_source",)


def test_underwriting_assumption_evidence_remains_assumed() -> None:
    # Given: a field is backed by an underwriting assumption rather than source evidence.
    evidence_id = EvidenceId("ev_assumption_market_rent")
    field = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("assumption.market_rent"),
            label="Market rent",
            value=2400,
            unit="usd",
            evidence_ids=(evidence_id,),
            source_priority=("market_comps",),
            fallback_sources=("underwriting_assumption",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.9,
            contradiction_status=ContradictionStatus.CLEAR,
        ),
    )
    snapshot = LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId("ls_assumption"),
        site_id=SiteId("site_assumption"),
        run_id=RunId("run_assumption"),
        fields=(field,),
        calculations=(),
        warnings=(),
        source_metadata=(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url="plotlot://assumptions/market-rent",
                source_title="Market rent assumption",
                source_type="underwriting_assumption",
                source_authority="underwriting_assumption",
                publisher="PlotLot",
                retrieved_at="2026-06-01T00:00:00+00:00",
                effective_date="2026-06-01",
                parser_version="assumption.v1",
                schema_version="lookup_snapshot_record.v1",
                raw_artifact_ref="assumptions/market-rent",
            ),
        ),
    )

    # When: source quality is applied while storing the lookup snapshot.
    stored = build_stored_lookup_snapshot(snapshot)
    stored_field = stored.snapshot.fields[0]

    # Then: the field remains visible only as an assumption, not a verified fact.
    assert stored_field.display_state is DisplayState.ASSUMED
    assert not stored_field.is_display_ready
    assert stored_field.confidence == 0.35
    assert stored_field.warnings == ("underwriting_assumption_source",)
