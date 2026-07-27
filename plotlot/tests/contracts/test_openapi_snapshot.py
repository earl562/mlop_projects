from __future__ import annotations

import hashlib
import json
from pathlib import Path

from plotlot.api.main import app
from plotlot.protocol.openapi import protocol_app, protocol_openapi_document
from scripts.contracts.export_openapi import export_openapi


def test_openapi_exposes_versioned_host_engine_protocol() -> None:
    # Given: the production PlotLot FastAPI application.
    production_paths = app.openapi()["paths"]

    # When: its dedicated protocol OpenAPI document is inspected.
    schema = protocol_openapi_document()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    # Then: production exposes the route while the boundary owns its schemas.
    assert "/api/v1/engine/opportunities" in production_paths
    assert "/api/v1/engine/opportunities" in paths
    assert "PlotLotHostContextV1" in components
    assert "ActorContextV1" in components


def test_openapi_export_is_byte_deterministic(tmp_path: Path) -> None:
    # Given: two independent output paths.
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    # When: the authoritative OpenAPI document is exported twice.
    export_openapi(first)
    protocol_app.openapi_schema = None
    export_openapi(second)

    # Then: both canonical byte streams and their hashes are identical.
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).hexdigest() == hashlib.sha256(second_bytes).hexdigest()
    assert json.loads(first_bytes)["info"]["version"] == "1.0.0"


def test_protocol_export_excludes_app_routes_unreachable_schemas_and_examples() -> None:
    # Given: the dedicated host-engine OpenAPI document.
    schema = protocol_openapi_document()
    expected_paths = {
        "/api/v1/engine/opportunities",
        "/api/v1/engine/runs/{engine_run_id}",
        "/api/v1/engine/runs/{engine_run_id}/cancel",
        "/api/v1/engine/runs/{engine_run_id}/events",
        "/api/v1/engine/runs/{engine_run_id}/evidence",
        "/api/v1/engine/runs/{engine_run_id}/report",
        "/api/v1/engine/runs/{engine_run_id}/replay",
        "/api/v1/engine/runs/{engine_run_id}/revisions/{engine_revision_id}",
    }

    # When: paths, components, and example-bearing fields are inspected.
    serialized = json.dumps(schema, sort_keys=True)
    components = schema["components"]["schemas"]

    # Then: unrelated product routes, types, and address examples cannot cross the boundary.
    assert set(schema["paths"]) == expected_paths
    assert "AnalyzeRequest" not in components
    assert '"example":' not in serialized
    assert '"examples":' not in serialized


def test_protocol_pagination_requires_event_and_evidence_cursors() -> None:
    # Given: the event and evidence list operations.
    paths = protocol_openapi_document()["paths"]
    event_parameters = paths["/api/v1/engine/runs/{engine_run_id}/events"]["get"]["parameters"]
    evidence_parameters = paths["/api/v1/engine/runs/{engine_run_id}/evidence"]["get"]["parameters"]

    # When: their query parameter contracts are inspected.
    event_cursor = next(item for item in event_parameters if item["name"] == "after_cursor")
    evidence_cursor = next(item for item in evidence_parameters if item["name"] == "cursor")

    # Then: neither operation permits an omitted cursor.
    assert event_cursor["required"] is True
    assert evidence_cursor["required"] is True
