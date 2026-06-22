from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.lookup_snapshot import FieldKey
from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_agent_run_endpoint_escalates_contradicted_zoning_snapshot(
    transport: ASGITransport,
) -> None:
    # Given: a recorded lookup snapshot has conflicting parcel and ordinance zoning.
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    contradicted_report = report(with_density_analysis=True)
    contradicted_report.property_record.zoning_code = "RM-2"
    snapshot = build_lookup_snapshot(contradicted_report)
    save_lookup_snapshot(snapshot)
    zoning_field = next(
        field for field in snapshot.fields if field.key == FieldKey("zoning.district")
    )
    run_id = f"run_{uuid4().hex}"

    assert zoning_field.display_state.value == "contradicted"
    assert "contradictory_sources" in zoning_field.warnings

    # When: the API starts an agent run from the contradicted lookup snapshot.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent-runs",
            json={
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "workspace_id": "ws_agent_contradiction",
                "project_id": "project_agent_contradiction",
                "run_id": run_id,
                "objective": "Decide whether zoning evidence is ready for synthesis.",
            },
        )

    # Then: the agent contract blocks synthesis and assigns human-review escalation.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_review"
    assert body["ready_for_synthesis"] is False
    assert "contradictory_sources" in body["warnings"]
    assert any(
        question == "zoning.district is contradicted; surface sources for human review before use."
        for question in body["open_questions"]
    )
    assert any(
        escalation["field_key"] == "zoning.district"
        and escalation["reason"] == "zoning.district is contradicted"
        and escalation["required_action"]
        == "Surface contradictory evidence for human review before use."
        for escalation in body["escalations"]
    )
    zoning_assignment = next(
        assignment
        for assignment in body["assignments"]
        if assignment["lane"] == "zoning_code_analyst"
    )
    assert zoning_assignment["escalation_required"] is True
    assert "zoning.district" in zoning_assignment["field_keys"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        trace_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/trace?workspace_id=ws_agent_contradiction"
        )

    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert "contradictory_sources" in trace["warnings"]
    assert any(
        question == "zoning.district is contradicted; surface sources for human review before use."
        for question in trace["open_questions"]
    )
