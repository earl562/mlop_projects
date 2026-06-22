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
from plotlot.pipeline.lookup_snapshot_store import (
    clear_lookup_snapshot_store,
    save_lookup_snapshot,
)
from plotlot.storage.db import get_session
from plotlot.storage.models import Document, EvalCaseResult, EvalRun, Report
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


async def _start_recorded_lookup_agent_run(
    transport: ASGITransport,
    *,
    workspace_id: str = "ws_api_agent",
    project_id: str = "project_api_agent",
    objective: str = "Find verified by-right development capacity.",
) -> tuple[str, dict, set[str], str]:
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
        response = await client.post(
            "/api/v1/agent-runs",
            json={
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "workspace_id": workspace_id,
                "project_id": project_id,
                "run_id": run_id,
                "objective": objective,
            },
        )

    assert response.status_code == 200
    body = response.json()
    return run_id, body, expected_evidence_ids, str(snapshot.lookup_snapshot_id)


@pytest.mark.asyncio
async def test_agent_run_endpoint_starts_run_from_recorded_lookup_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: a lookup snapshot is already recorded in the evidence kernel.
    (
        run_id,
        body,
        expected_evidence_ids,
        lookup_snapshot_id,
    ) = await _start_recorded_lookup_agent_run(transport)

    # Then: the response exposes replayable plan, evidence, and trace data.
    assert body["run_id"] == run_id
    assert body["lookup_snapshot_id"] == lookup_snapshot_id
    assert body["status"] == "requires_review"
    assert body["ready_for_synthesis"] is False
    assert set(body["evidence_ids"]) == expected_evidence_ids
    assert {assignment["lane"] for assignment in body["assignments"]} == {
        "parcel_analyst",
        "zoning_code_analyst",
        "gis_layer_analyst",
        "entitlement_risk_analyst",
        "underwriting_analyst",
        "evidence_reviewer",
        "report_document_analyst",
        "lead_developer_consultant",
    }
    assert body["trace_steps"][0]["kind"] == "run_started"
    assert body["trace_steps"][-1]["kind"] == "run_completed"
    assert all(step["sequence"] == index for index, step in enumerate(body["trace_steps"], start=1))


@pytest.mark.asyncio
async def test_agent_run_endpoint_returns_stored_state_and_reproducible_summary_artifact(
    transport: ASGITransport,
) -> None:
    run_id, body, expected_evidence_ids, _ = await _start_recorded_lookup_agent_run(transport)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stored_response = await client.get(f"/api/v1/agent-runs/{run_id}?workspace_id=ws_api_agent")

    assert stored_response.status_code == 200
    stored_body = stored_response.json()
    assert stored_body["run_id"] == body["run_id"]
    assert stored_body["lookup_snapshot_id"] == body["lookup_snapshot_id"]
    assert stored_body["trace_steps"] == body["trace_steps"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        artifact_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/summary-artifact?workspace_id=ws_api_agent"
        )

    assert artifact_response.status_code == 200
    artifact = artifact_response.json()
    expected_report_id = agent_run_report_id(run_id)
    expected_document_id = agent_run_document_id(run_id)
    assert artifact["status"] == "draft"
    assert artifact["report_id"] == expected_report_id
    assert artifact["document_id"] == expected_document_id
    assert set(artifact["evidence_ids"]) == expected_evidence_ids

    report_json = artifact["report_json"]
    assert report_json["generated_by"] == "agent_run_summary"
    assert report_json["run_id"] == body["run_id"]
    assumptions = report_json["assumptions"]
    assert assumptions
    assert any(
        assumption["key"].startswith("open_question.")
        and "standards.setbacks.front is unknown" in assumption["text"]
        and assumption["status"] == "requires_human_review"
        for assumption in assumptions
    )
    assert all("evidence_ids" not in assumption for assumption in assumptions)
    material_claims = [
        claim
        for section in report_json["sections"]
        for claim in section["claims"]
        if claim["material"]
    ]
    assert material_claims
    assert all(claim["evidence_ids"] for claim in material_claims)
    calculation_claims = [
        claim for claim in material_claims if claim["key"].startswith("calculation.")
    ]
    assert any("max_units=2" in claim["text"] for claim in calculation_claims)

    clear_agent_run_store()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        durable_response = await client.get(
            f"/api/v1/agent-runs/{run_id}?workspace_id=ws_api_agent"
        )

    assert durable_response.status_code == 200
    durable_body = durable_response.json()
    assert durable_body["run_id"] == body["run_id"]
    assert durable_body["lookup_snapshot_id"] == body["lookup_snapshot_id"]
    assert durable_body["trace_steps"] == body["trace_steps"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        durable_artifact_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/summary-artifact?workspace_id=ws_api_agent"
        )

    assert durable_artifact_response.status_code == 200
    durable_artifact = durable_artifact_response.json()
    assert durable_artifact["report_id"] == expected_report_id
    assert durable_artifact["document_id"] == expected_document_id
    assert durable_artifact["report_json"]["run_id"] == body["run_id"]
    assert durable_artifact["report_json"]["sections"] == report_json["sections"]
    assert durable_artifact["report_json"]["assumptions"] == assumptions

    session = await get_session()
    try:
        report_row = await session.get(Report, expected_report_id)
        document_row = await session.get(Document, expected_document_id)
    finally:
        await session.close()

    assert report_row is not None
    assert report_row.analysis_run_id == body["run_id"]
    assert set(report_row.evidence_ids) == expected_evidence_ids
    assert report_row.report_json["run_id"] == body["run_id"]
    assert document_row is not None
    assert document_row.report_id == expected_report_id
    assert document_row.document_type == "agent_run_summary"


@pytest.mark.asyncio
async def test_agent_run_endpoint_evaluates_lookup_run_and_tracks_improvement(
    transport: ASGITransport,
) -> None:
    run_id, body, expected_evidence_ids, _ = await _start_recorded_lookup_agent_run(transport)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        eval_response = await client.post(
            f"/api/v1/agent-runs/{run_id}/evals?workspace_id=ws_api_agent"
        )

    assert eval_response.status_code == 200
    eval_body = eval_response.json()
    assert eval_body["status"] == "passed"
    assert eval_body["metrics"]["evidence_coverage"] == 1.0
    assert eval_body["metrics"]["artifact_citation_coverage"] == 1.0
    assert eval_body["metrics"]["opportunity_hypothesis_completeness"] == 1.0
    assert eval_body["metrics"]["assumption_label_coverage"] == 1.0
    assert eval_body["diffs"]["unsupported_claim_keys"] == []
    assert eval_body["diffs"]["incomplete_opportunity_keys"] == []
    assert eval_body["diffs"]["missing_assumption_keys"] == []

    session = await get_session()
    try:
        eval_run = await session.get(EvalRun, eval_body["eval_run_id"])
        eval_case_result = await session.get(EvalCaseResult, eval_body["eval_case_result_id"])
    finally:
        await session.close()

    assert eval_run is not None
    assert eval_run.suite == "agent_run_lookup_correctness"
    assert eval_run.status == "passed"
    assert eval_case_result is not None
    assert eval_case_result.status == "passed"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        latest_eval_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/evals/latest?workspace_id=ws_api_agent"
        )

    assert latest_eval_response.status_code == 200
    latest_eval = latest_eval_response.json()
    assert latest_eval["eval_run_id"] == eval_body["eval_run_id"]
    assert latest_eval["eval_case_result_id"] == eval_body["eval_case_result_id"]
    assert latest_eval["status"] == "passed"
    assert latest_eval["metrics"]["evidence_coverage"] == 1.0
    assert latest_eval["metrics"]["opportunity_hypothesis_completeness"] == 1.0
    assert latest_eval["diffs"]["run_id"] == body["run_id"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        improvement_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/improvement-summary?workspace_id=ws_api_agent"
        )

    assert improvement_response.status_code == 200
    improvement = improvement_response.json()
    assert improvement["current"]["eval_run_id"] == eval_body["eval_run_id"]
    assert improvement["release_blocked"] is False
    if improvement["previous"] is None:
        assert improvement["baseline_status"] == "missing"
        assert improvement["improvement_status"] == "no_baseline"
        assert improvement["deltas"] == {}
    else:
        assert improvement["baseline_status"] == "available"
        assert improvement["regressed_metric_keys"] == []
        if improvement["improvement_status"] == "flat":
            assert improvement["deltas"]["evidence_coverage"] == 0.0
            assert improvement["improved_metric_keys"] == []
        elif improvement["improvement_status"] == "improved":
            assert improvement["improved_metric_keys"]
            assert any(delta > 0 for delta in improvement["deltas"].values())
        else:
            pytest.fail(f"Unexpected improvement status: {improvement['improvement_status']}")

    underwriting = next(
        assignment
        for assignment in body["assignments"]
        if assignment["lane"] == "underwriting_analyst"
    )
    assert underwriting["calculation_outputs"] == ["max_units=2"]


@pytest.mark.asyncio
async def test_agent_run_endpoint_returns_404_for_unknown_lookup_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: no lookup snapshot exists for the requested ID.
    clear_agent_run_store()
    clear_lookup_snapshot_store()

    # When: the API starts a run from a missing snapshot.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent-runs",
            json={
                "lookup_snapshot_id": "ls_missing",
                "workspace_id": "ws_api_agent",
                "objective": "Assess development capacity.",
            },
        )

    # Then: the API refuses to create a run without recorded evidence.
    assert response.status_code == 404
    assert response.json()["detail"] == "Lookup snapshot not found"


@pytest.mark.asyncio
async def test_agent_run_endpoint_returns_404_for_unknown_run(
    transport: ASGITransport,
) -> None:
    clear_agent_run_store()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent-runs/run_missing?workspace_id=ws_api_agent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent run not found"
