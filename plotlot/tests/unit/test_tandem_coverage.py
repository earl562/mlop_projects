"""Tests for the MCP OpenData + Municode tandem coverage runner."""

from __future__ import annotations

import pytest

from plotlot.harness.runtime import ToolCallResult
from plotlot.harness.tandem_coverage import CountySeed, _classify_county, evaluate_county
from plotlot.land_use.models import PolicyDecision


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, *, name, arguments, context, approval_id=None):  # noqa: ANN001, ARG002
        self.calls.append((name, arguments))
        payloads = {
            "discover_open_data_layers": {
                "status": "success",
                "results": [{"title": "Wake Parcels"}, {"title": "Wake Zoning"}],
            },
            "search_properties": {
                "status": "success",
                "total_results": 1,
                "sample": [{"folio": "1703", "county": "Wake"}],
            },
            "discover_municode_authorities": {
                "status": "success",
                "results": [
                    {
                        "municipality": "Wake County",
                        "county": "wake",
                        "state": "NC",
                        "zoning_node_id": "WAKE_ZONING",
                    }
                ],
            },
            "search_municode_live": {
                "status": "success",
                "results": [{"heading": "Setbacks", "snippet": "Front yard setback."}],
            },
        }
        return ToolCallResult(
            tool_name=name,
            decision=PolicyDecision(allowed=True, reason="test"),
            status="ok",
            result=payloads[name],
        )


@pytest.mark.asyncio
async def test_evaluate_county_drives_opendata_property_and_municode_tools():
    adapter = _FakeAdapter()
    seed = CountySeed(
        state="NC",
        state_fips="37",
        geoid="37183",
        county="Wake",
        county_label="Wake County",
        lat=35.79,
        lng=-78.65,
    )

    result = await evaluate_county(
        adapter,  # type: ignore[arg-type]
        seed,
        property_search="when-open-data",
        timeout_seconds=5,
    )

    assert result["tandem_status"] == "ok"
    assert [name for name, _ in adapter.calls] == [
        "discover_open_data_layers",
        "search_properties",
        "discover_municode_authorities",
        "search_municode_live",
        "search_municode_live",
        "search_municode_live",
    ]
    assert adapter.calls[0][1]["state"] == "NC"
    assert adapter.calls[1][1]["max_results"] == 1
    assert adapter.calls[3][1]["municipality"] == "Wake County"


def test_classify_county_separates_property_and_ordinance_gaps():
    assert (
        _classify_county(
            layer_count=1,
            property_status="success",
            property_count=0,
            authority_count=1,
            ordinance_hit_count=3,
        )
        == "partial_no_property_matches"
    )
    assert (
        _classify_county(
            layer_count=1,
            property_status="success",
            property_count=1,
            authority_count=1,
            ordinance_hit_count=0,
        )
        == "partial_no_ordinance_hits"
    )
