"""Unit tests for hub_discovery Options 2 and 3 (state servers + URL patterns).

All HTTP calls are mocked — no live ArcGIS requests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.property.hub_discovery import (
    _probe_arcgis_server,
    _probe_county_url_patterns,
    _search_state_servers,
)
from plotlot.property.models import DatasetInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAT = 35.2271
_LNG = -80.8431
_COUNTY = "Mecklenburg"
_STATE = "NC"


def _make_dataset(name: str = "Test Dataset") -> DatasetInfo:
    return DatasetInfo(
        dataset_id="test-id",
        name=name,
        url="https://example.com/arcgis/rest/services/TestSvc/MapServer",
        layer_id=0,
        dataset_type="parcels",
        county=_COUNTY,
        state=_STATE,
        fields=["PARCEL_ID", "OWNER", "ACRES", "ADDRESS"],
        discovered_at=datetime.now(timezone.utc),
    )


def _json_resp(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


# ---------------------------------------------------------------------------
# _probe_arcgis_server tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_arcgis_server_returns_none_on_dead_server() -> None:
    """When the root request fails, returns None immediately."""
    with patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_cls.return_value = mock_client

        result = await _probe_arcgis_server(
            "https://gis.deadserver.gov/arcgis/rest/services",
            _COUNTY,
            _STATE,
            "parcels",
            _LAT,
            _LNG,
        )

    assert result is None


@pytest.mark.asyncio
async def test_probe_arcgis_server_finds_parcel_layer() -> None:
    """Finds a parcel layer when the ArcGIS tree is crawled."""
    root_data = {
        "folders": ["Assessor"],
        "services": [],
    }
    folder_data = {"services": [{"name": "Assessor/Parcels", "type": "MapServer"}]}
    service_data = {"layers": [{"id": 0, "name": "Parcel Fabric", "type": "Feature Layer"}]}
    layer_data = {
        "name": "Parcel Fabric",
        "fields": [
            {"name": "PARCEL_ID"},
            {"name": "OWNER"},
            {"name": "ACRES"},
            {"name": "SITE_ADDRESS"},
        ],
    }

    call_count = [0]

    def _get_response(url: str, params: dict | None = None):
        call_count[0] += 1
        if url.endswith("/services"):
            return _json_resp(root_data)
        if "Assessor" in url and "Parcels" not in url:
            return _json_resp(folder_data)
        if "MapServer" in url and url.split("/")[-1].isdigit():
            return _json_resp(layer_data)
        if "MapServer" in url:
            return _json_resp(service_data)
        return _json_resp({})

    with (
        patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls,
        patch("plotlot.property.hub_discovery._has_coverage", new=AsyncMock(return_value=True)),
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_get_response)
        mock_cls.return_value = mock_client

        result = await _probe_arcgis_server(
            "https://example.gov/arcgis/rest/services",
            _COUNTY,
            _STATE,
            "parcels",
            _LAT,
            _LNG,
        )

    assert result is not None
    assert "Parcel" in result.name or "Assessor" in result.name


@pytest.mark.asyncio
async def test_probe_arcgis_server_skips_no_coverage() -> None:
    """Candidate layers that fail coverage check are skipped."""
    root_data = {"folders": [], "services": [{"name": "ParcelsService", "type": "MapServer"}]}
    service_data = {"layers": [{"id": 0, "name": "Parcels", "type": "Feature Layer"}]}
    layer_data = {
        "name": "Parcels",
        "fields": [{"name": "PARCEL_ID"}, {"name": "ACRES"}],
    }

    def _get_response(url: str, params: dict | None = None):
        if url.split("/")[-1].isdigit():
            return _json_resp(layer_data)
        if "ParcelsService/MapServer" in url:
            return _json_resp(service_data)
        return _json_resp(root_data)

    with (
        patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls,
        patch("plotlot.property.hub_discovery._has_coverage", new=AsyncMock(return_value=False)),
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_get_response)
        mock_cls.return_value = mock_client

        result = await _probe_arcgis_server(
            "https://example.gov/arcgis/rest/services",
            _COUNTY,
            _STATE,
            "parcels",
            _LAT,
            _LNG,
        )

    assert result is None


# ---------------------------------------------------------------------------
# _search_state_servers tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_state_servers_returns_none_for_unknown_state() -> None:
    """State without an entry in _STATE_SERVERS returns None immediately."""
    result = await _search_state_servers(_LAT, _LNG, "SomeCounty", "ZZ", dataset_type="parcels")
    assert result is None


@pytest.mark.asyncio
async def test_search_state_servers_calls_probe_for_known_state() -> None:
    """For NC, probes the nconemap.gov server."""
    expected = _make_dataset("NC Parcels")

    with patch(
        "plotlot.property.hub_discovery._probe_arcgis_server",
        new=AsyncMock(return_value=expected),
    ) as mock_probe:
        result = await _search_state_servers(_LAT, _LNG, _COUNTY, "NC", dataset_type="parcels")

    assert result is expected
    mock_probe.assert_called_once()
    # First positional arg is the server URL — should be the NC server
    call_args = mock_probe.call_args
    assert "nconemap" in call_args.args[0]


@pytest.mark.asyncio
async def test_search_state_servers_tries_next_on_none() -> None:
    """If first server returns None and there are more, tries them in order."""
    # Temporarily inject a state with two servers for this test
    from plotlot.property import hub_discovery as hd

    original = hd._STATE_SERVERS.copy()
    hd._STATE_SERVERS["xx"] = [
        "https://first.example.gov/arcgis/rest/services",
        "https://second.example.gov/arcgis/rest/services",
    ]
    expected = _make_dataset("Second Server Dataset")
    results_iter = iter([None, expected])

    try:
        with patch(
            "plotlot.property.hub_discovery._probe_arcgis_server",
            new=AsyncMock(side_effect=lambda *a, **kw: next(results_iter)),
        ) as mock_probe:
            result = await _search_state_servers(
                _LAT, _LNG, "TestCounty", "xx", dataset_type="parcels"
            )

        assert result is expected
        assert mock_probe.call_count == 2
    finally:
        hd._STATE_SERVERS = original


# ---------------------------------------------------------------------------
# _probe_county_url_patterns tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_county_url_patterns_returns_none_when_no_live_servers() -> None:
    """When no URL patterns respond with 200, returns None."""
    with patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        # All requests raise (server unreachable)
        mock_client.get = AsyncMock(side_effect=Exception("unreachable"))
        mock_cls.return_value = mock_client

        result = await _probe_county_url_patterns(
            _LAT, _LNG, _COUNTY, _STATE, dataset_type="parcels"
        )

    assert result is None


@pytest.mark.asyncio
async def test_probe_county_url_patterns_probes_live_server() -> None:
    """When a URL pattern responds live, _probe_arcgis_server is called for it."""
    expected = _make_dataset("County Parcels")

    def _head(url: str, params: dict | None = None):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"folders": [], "services": []}
        return resp

    with (
        patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls,
        patch(
            "plotlot.property.hub_discovery._probe_arcgis_server",
            new=AsyncMock(return_value=expected),
        ),
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_head)
        mock_cls.return_value = mock_client

        result = await _probe_county_url_patterns(
            _LAT, _LNG, _COUNTY, _STATE, dataset_type="parcels"
        )

    assert result is expected


@pytest.mark.asyncio
async def test_probe_county_url_patterns_slug_generation() -> None:
    """County slug removes spaces; state slug is lowercased 2-letter code."""
    slugs_seen: list[str] = []

    async def _capture_probe(base_url: str, *args, **kwargs) -> DatasetInfo | None:
        slugs_seen.append(base_url)
        return None

    def _live(url: str, params: dict | None = None):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {}
        return resp

    with (
        patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls,
        patch(
            "plotlot.property.hub_discovery._probe_arcgis_server",
            new=AsyncMock(side_effect=_capture_probe),
        ),
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_live)
        mock_cls.return_value = mock_client

        await _probe_county_url_patterns(_LAT, _LNG, "Los Angeles", "CA", dataset_type="parcels")

    # At least one URL should contain "losangeles" (spaces removed)
    assert any("losangeles" in url for url in slugs_seen), (
        f"Expected 'losangeles' in at least one URL, got: {slugs_seen[:5]}"
    )
