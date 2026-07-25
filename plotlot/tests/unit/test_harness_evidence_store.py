from __future__ import annotations

from plotlot.harness.contracts import (
    ApplicabilityStatus,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
    RunId,
    SourceMode,
)
from plotlot.harness.evidence_store import LocalEvidenceLedger


def test_local_evidence_ledger_saves_lists_and_reads_by_id(tmp_path) -> None:
    # Given: an empty local evidence ledger and a typed fixture GIS evidence item.
    ledger = LocalEvidenceLedger(tmp_path / "evidence.json")
    evidence = EvidenceItem(
        evidence_id=EvidenceId("ev_fixture_001"),
        run_id=RunId("run_fixture_001"),
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name="South Florida GIS Fixture",
        source_url="fixture://south-florida-gis",
        provider="fixture",
        jurisdiction="South Florida",
        freshness_status=FreshnessStatus.FIXTURE,
        applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
        normalized_text="Fixture GIS evidence for a preliminary run.",
        confidence=0.5,
        source_mode=SourceMode.FIXTURE,
    )

    # When: the evidence item is persisted.
    saved = ledger.save_evidence(evidence)

    # Then: it can be retrieved by id and listed by run.
    assert saved.evidence_id == "ev_fixture_001"
    assert ledger.get_evidence(EvidenceId("ev_fixture_001")) == evidence
    assert ledger.list_evidence(run_id=RunId("run_fixture_001")) == [evidence]


def test_local_evidence_ledger_orders_evidence_by_retrieved_at_then_id(tmp_path) -> None:
    # Given: a local evidence ledger with two evidence records for one run.
    ledger = LocalEvidenceLedger(tmp_path / "evidence.json")
    first = EvidenceItem(
        evidence_id=EvidenceId("ev_fixture_001"),
        run_id=RunId("run_fixture_001"),
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name="GIS one",
        source_url="fixture://one",
        provider="fixture",
        jurisdiction="South Florida",
        freshness_status=FreshnessStatus.FIXTURE,
        applicability=ApplicabilityStatus.UNKNOWN,
        confidence=0.5,
        source_mode=SourceMode.FIXTURE,
    )
    second = first.model_copy(
        update={"evidence_id": EvidenceId("ev_fixture_002"), "source_name": "GIS two"}
    )

    # When: both evidence items are persisted out of id order.
    ledger.save_evidence(second)
    ledger.save_evidence(first)

    # Then: list output is deterministic by evidence id for matching timestamps.
    assert [item.evidence_id for item in ledger.list_evidence()] == [
        "ev_fixture_001",
        "ev_fixture_002",
    ]
