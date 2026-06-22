from __future__ import annotations

import pytest

from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_repository import (
    LookupSnapshotPersistenceContext,
    persist_lookup_snapshot,
)
from plotlot.storage.models import AnalysisRun, EvidenceItem
from tests.unit.lookup_snapshot_repository_fixtures import FakePersistenceSession, report


@pytest.mark.asyncio
async def test_persist_lookup_snapshot_records_calculation_output_lineage() -> None:
    # Given: a lookup snapshot whose deterministic calculation uses recorded evidence.
    session = FakePersistenceSession()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))

    # When: the snapshot is persisted into the harness spine.
    stored = await persist_lookup_snapshot(
        session,
        snapshot,
        LookupSnapshotPersistenceContext(request_address="7940 Plantation Blvd"),
    )

    # Then: evidence and trace records name the calculation output they support.
    run = await session.get(AnalysisRun, str(snapshot.lookup_snapshot_id))
    evidence_items = [row for row in session.added if isinstance(row, EvidenceItem)]
    calculation_records = [
        record for record in stored.evidence_records if record.calculation_outputs
    ]
    assert run is not None
    assert len(calculation_records) == 2
    for record in calculation_records:
        assert record.calculation_outputs == ("max_units=2",)
        assert "source -> normalized evidence -> calculation output:max_units=2" in record.lineage
    persisted_records = run.output_json["evidence_records"]
    assert all(
        "max_units=2" in record["calculation_outputs"]
        for record in persisted_records
        if record["calculation_outputs"]
    )
    assert all(
        item.metadata_json["calculation_outputs"] == ["max_units=2"]
        for item in evidence_items
        if item.metadata_json["calculation_outputs"]
    )
    trace_record = run.output_json["trace_record"]
    calc_field_trace = [
        field for field in trace_record["field_evidence"] if field["field_key"] == "calc.max_units"
    ]
    assert len(calc_field_trace) == 1
    assert calc_field_trace[0]["evidence_ids"] == trace_record["evidence_ids"]
    assert trace_record["calculation_traces"] == [
        {
            "calculator_name": "max_units",
            "calculator_version": "2026.06.21",
            "formula": "lot_area_sqft constrained by density, lot area, parking, and dimensions",
            "input_evidence_ids": trace_record["evidence_ids"],
            "output_label": "max_units=2",
            "warnings": ["Density limited to two units."],
            "is_reproducible": True,
        }
    ]
