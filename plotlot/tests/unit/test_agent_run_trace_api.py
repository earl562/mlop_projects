from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.harness.agent_run_artifact_repository import (
    agent_run_document_id,
    agent_run_report_id,
)
from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_agent_run_trace_endpoint_returns_replay_package_after_eval(
    transport: ASGITransport,
) -> None:
    # Given: a lookup snapshot can seed an agent run with durable evidence and eval data.
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    expected_evidence_ids = {
        str(evidence_id) for field in snapshot.fields for evidence_id in field.evidence_ids
    } | {
        str(evidence_id)
        for calculation in snapshot.calculations
        for evidence_id in calculation.input_evidence_ids
    }
    run_id = f"run_{uuid4().hex}"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/agent-runs",
            json={
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "workspace_id": "ws_trace_agent",
                "project_id": "project_trace_agent",
                "site_id": "site_trace_agent",
                "run_id": run_id,
                "objective": "Replay verified development capacity.",
            },
        )
        eval_response = await client.post(
            f"/api/v1/agent-runs/{run_id}/evals?workspace_id=ws_trace_agent"
        )

        # When: the API requests the replay trace package for the run.
        trace_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/trace?workspace_id=ws_trace_agent"
        )

    # Then: the package connects run state, trace steps, artifacts, and eval gates.
    assert start_response.status_code == 200
    assert eval_response.status_code == 200
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["run_id"] == run_id
    assert trace["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert trace["workspace_id"] == "ws_trace_agent"
    assert trace["project_id"] == "project_trace_agent"
    assert trace["site_id"] == "site_trace_agent"
    assert trace["replay_ready"] is True
    assert trace["missing_replay_requirements"] == []
    assert set(trace["evidence_ids"]) == expected_evidence_ids
    assert {packet["evidence_id"] for packet in trace["evidence_packets"]} == expected_evidence_ids
    assert {source["evidence_id"] for source in trace["source_retrievals"]} == expected_evidence_ids
    assert all(source["retrieved_at"] for source in trace["source_retrievals"])
    assert all(source["parser_version"] for source in trace["source_retrievals"])
    assert all(source["schema_version"] for source in trace["source_retrievals"])
    assert all(source["raw_artifact_ref"] for source in trace["source_retrievals"])
    assert all(source["lineage"] for source in trace["source_retrievals"])
    assert all(
        "source_url" in source and "missing_source_url" in source["quality_flags"]
        for source in trace["source_retrievals"]
    )
    assert {packet["source_authority"] for packet in trace["evidence_packets"]} == {
        "official_assessor",
        "official_zoning_ordinance",
    }
    assert all(packet["quality_score"] == 0.0 for packet in trace["evidence_packets"])
    assert all(
        "missing_source_url" in packet["quality_flags"] for packet in trace["evidence_packets"]
    )
    assert all(
        "missing_effective_date" in packet["quality_flags"] for packet in trace["evidence_packets"]
    )
    assert all(packet["lineage"] for packet in trace["evidence_packets"])
    assert trace["trace_steps"][0]["kind"] == "run_started"
    assert trace["trace_steps"][-1]["kind"] == "run_completed"
    assert all(
        step["sequence"] == index for index, step in enumerate(trace["trace_steps"], start=1)
    )
    assert {assignment["lane"] for assignment in trace["assignments"]} == {
        "parcel_analyst",
        "zoning_code_analyst",
        "gis_layer_analyst",
        "entitlement_risk_analyst",
        "underwriting_analyst",
        "evidence_reviewer",
        "report_document_analyst",
        "lead_developer_consultant",
    }
    assert trace["artifact"]["status"] == "draft"
    assert trace["artifact"]["report_id"] == agent_run_report_id(run_id)
    assert trace["artifact"]["document_id"] == agent_run_document_id(run_id)
    assert set(trace["artifact"]["evidence_ids"]) == expected_evidence_ids
    sections = trace["artifact"]["sections"]
    assert {section["id"] for section in sections} == {
        "evidence_scope",
        "deterministic_calculations",
    }
    assert all(set(section["evidence_ids"]).issubset(expected_evidence_ids) for section in sections)
    claims = [claim for section in sections for claim in section["claims"]]
    assert claims
    assert all(set(claim["evidence_ids"]).issubset(expected_evidence_ids) for claim in claims)
    assert any(claim["key"].startswith("calculation.") for claim in claims)
    assumptions = trace["artifact"]["assumptions"]
    assert assumptions
    assert any(
        assumption["key"].startswith("open_question.")
        and "standards.setbacks.front is unknown" in assumption["text"]
        and assumption["status"] == "requires_human_review"
        for assumption in assumptions
    )
    assert all("evidence_ids" not in assumption for assumption in assumptions)
    opportunities = trace["artifact"]["opportunities"]
    assert opportunities
    by_right = opportunities[0]
    assert by_right["key"] == "opportunity.by_right_capacity"
    assert by_right["status"] == "hypothesis"
    assert (
        by_right["current_verified_condition"] == "Recorded lookup evidence supports max_units=2."
    )
    assert (
        by_right["proposed_scenario"]
        == "Test by-right development capacity using recorded zoning evidence."
    )
    assert (
        by_right["upside_mechanism"]
        == "Developer value may exist if the by-right unit yield exceeds the current use."
    )
    assert by_right["blocking_constraints"]
    assert by_right["assumptions"]
    assert (
        by_right["next_verification_step"]
        == "Confirm market rents, costs, financing terms, and any missing dimensional standards before underwriting value."
    )
    assert 0 < by_right["confidence"] <= 1
    assert set(by_right["evidence_ids"]).issubset(expected_evidence_ids)
    assert by_right["calculation_outputs"] == ["max_units=2"]
    assert trace["latest_eval"]["status"] == "passed"
    assert "evidence_coverage" in trace["latest_eval"]["metric_keys"]
    assert trace["improvement"]["release_blocked"] is False
    assert trace["improvement"]["regressed_metric_keys"] == []
    improvement_log = trace["improvement"]["improvement_log"]
    assert isinstance(improvement_log, list)
    if improvement_log:
        assert improvement_log[0]["changed_rule"].startswith("eval_metric:")
