"""Unit tests for parcel terrain analysis.

The elevation service is mocked — these never touch nationalmap.gov. Synthetic
surfaces (flat, planar slope, cliff) make the expected slope arithmetically
known, so a regression in the gradient math is unambiguous.
"""

from __future__ import annotations

import json

import httpx
import pytest

from plotlot.property.terrain import (
    STEEP_GRADIENT_PCT,
    TerrainAnalysis,
    _point_in_polygon,
    analyze_terrain,
)

# ~40 m square parcel near Point Loma.
PARCEL = [
    [-117.2410, 32.6790],
    [-117.2406, 32.6790],
    [-117.2406, 32.6794],
    [-117.2410, 32.6794],
    [-117.2410, 32.6790],
]


def _elevation_client(surface) -> httpx.AsyncClient:
    """Mock 3DEP: `surface(lng, lat)` returns metres for each requested point."""

    def handler(request: httpx.Request) -> httpx.Response:
        geometry = json.loads(request.url.params["geometry"])
        samples = [
            {"locationId": i, "value": surface(lng, lat)}
            for i, (lng, lat) in enumerate(geometry["points"])
        ]
        return httpx.Response(200, json={"samples": samples})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def flat(_lng: float, _lat: float) -> float:
    return 100.0


def planar_30pct(lng: float, _lat: float) -> float:
    """0.30 m rise per metre east — a 30% grade."""
    metres_east = (lng + 117.2410) * 111_320.0 * 0.8425  # cos(32.679 deg)
    return 100.0 + 0.30 * metres_east


# ── Geometry helper ──────────────────────────────────────────────────────────


def test_point_in_polygon_inside_and_outside() -> None:
    assert _point_in_polygon(-117.2408, 32.6792, PARCEL)
    assert not _point_in_polygon(-117.2500, 32.6792, PARCEL)
    assert not _point_in_polygon(-117.2408, 32.6900, PARCEL)


# ── Slope measurement ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flat_parcel_is_not_slope_constrained() -> None:
    async with _elevation_client(flat) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    assert terrain.mean_slope_pct == pytest.approx(0.0, abs=0.5)
    assert terrain.elevation_differential_ft == pytest.approx(0.0, abs=0.5)
    assert terrain.steep_fraction == 0.0
    assert terrain.is_steep_hillside is False
    assert terrain.slope_constrained is False
    assert terrain.yield_caveat() == ""


@pytest.mark.asyncio
async def test_planar_slope_is_measured_accurately() -> None:
    """A known 30% grade must read back as ~30%, not merely 'steep'."""
    async with _elevation_client(planar_30pct) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    assert terrain.mean_slope_pct == pytest.approx(30.0, rel=0.1)
    assert terrain.steep_fraction == 1.0
    assert terrain.slope_constrained is True


@pytest.mark.asyncio
async def test_steep_grade_with_enough_relief_meets_the_ordinance_test() -> None:
    """Both limbs required: >=25% gradient AND >=50 ft of relief."""
    async with _elevation_client(planar_30pct) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    assert terrain.elevation_differential_ft >= 50.0
    assert terrain.is_steep_hillside is True
    assert "25%" in terrain.steep_basis


@pytest.mark.asyncio
async def test_steep_but_shallow_relief_is_flagged_without_claiming_the_ordinance() -> None:
    """A short steep bank is constrained for our purposes but is not a "steep
    hillside" under SDMC, which also requires 50 ft of elevation differential.
    Asserting the ordinance applies when it does not would be a false citation."""

    def short_steep(lng: float, _lat: float) -> float:
        # 30% grade across the parcel only; flat plateaus either side, so total
        # relief stays under 50 ft even though the parcel itself is steep.
        west, east = -117.2410, -117.2406
        metres_east = (min(max(lng, west), east) - west) * 111_320.0 * 0.8425
        return 100.0 + 0.30 * metres_east

    async with _elevation_client(short_steep) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    assert terrain.elevation_differential_ft < 50.0
    assert terrain.is_steep_hillside is False
    assert terrain.slope_constrained is True
    assert "upper bound" in terrain.yield_caveat()


@pytest.mark.asyncio
async def test_caveat_cites_the_ordinance_only_when_it_applies() -> None:
    async with _elevation_client(planar_30pct) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    caveat = terrain.yield_caveat()
    assert "steep-hillside definition" in caveat
    assert "Environmentally Sensitive Lands" in caveat


# ── Graceful degradation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_geometry_returns_none() -> None:
    assert await analyze_terrain(None) is None
    assert await analyze_terrain([]) is None
    assert await analyze_terrain([[-117.2, 32.6], [-117.1, 32.7]]) is None


@pytest.mark.asyncio
async def test_service_failure_returns_none_rather_than_raising() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        assert await analyze_terrain(PARCEL, client=client) is None


@pytest.mark.asyncio
async def test_service_error_payload_returns_none() -> None:
    def err(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": 500, "message": "boom"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(err)) as client:
        assert await analyze_terrain(PARCEL, client=client) is None


@pytest.mark.asyncio
async def test_nodata_samples_do_not_crash_the_analysis() -> None:
    def sparse(request: httpx.Request) -> httpx.Response:
        geometry = json.loads(request.url.params["geometry"])
        samples = [
            {"locationId": i, "value": "NoData" if i % 3 else 100.0}
            for i, _ in enumerate(geometry["points"])
        ]
        return httpx.Response(200, json={"samples": samples})

    async with httpx.AsyncClient(transport=httpx.MockTransport(sparse)) as client:
        terrain = await analyze_terrain(PARCEL, client=client)

    assert terrain is not None
    assert terrain.sample_count > 0


@pytest.mark.asyncio
async def test_all_nodata_returns_none() -> None:
    def nodata(request: httpx.Request) -> httpx.Response:
        geometry = json.loads(request.url.params["geometry"])
        return httpx.Response(
            200,
            json={
                "samples": [
                    {"locationId": i, "value": "NoData"} for i, _ in enumerate(geometry["points"])
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(nodata)) as client:
        assert await analyze_terrain(PARCEL, client=client) is None


# ── Reporting surface ────────────────────────────────────────────────────────


def test_summary_reports_slope_and_source() -> None:
    terrain = TerrainAnalysis(
        mean_slope_pct=27.0,
        max_slope_pct=43.0,
        elevation_min_ft=100.0,
        elevation_max_ft=181.0,
        elevation_differential_ft=81.0,
        steep_fraction=0.75,
        sample_count=40,
        is_steep_hillside=True,
        slope_constrained=True,
        steep_basis="27% average gradient with 81 ft of relief",
        resolution_note="10x10 grid, ~14 m spacing",
    )
    summary = terrain.summary()

    assert "27%" in summary
    assert "75%" in summary
    assert "81 ft" in summary
    assert "USGS 3DEP" in summary
    assert str(int(STEEP_GRADIENT_PCT)) in summary
