"""Tests for the geometry / buildable envelope endpoint.

Covers: basic computation, zero setbacks, setbacks exceeding lot,
FAR-limited height, lot coverage constraint, polygon vertices, and area math.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestEnvelopeEndpoint:
    """POST /api/v1/geometry/envelope tests."""

    @pytest.mark.asyncio
    async def test_basic_envelope(self, client: AsyncClient):
        """50x100 lot with 25/10/20 setbacks and 35ft height."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 50,
                "lot_depth_ft": 100,
                "setback_front_ft": 25,
                "setback_side_ft": 10,
                "setback_rear_ft": 20,
                "max_height_ft": 35,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Lot area
        assert data["lot_area_sqft"] == 5000.0

        # Buildable dimensions: width = 50 - 2*10 = 30, depth = 100 - 25 - 20 = 55
        assert data["buildable_width_ft"] == 30.0
        assert data["buildable_depth_ft"] == 55.0
        assert data["buildable_footprint_sqft"] == 30.0 * 55.0  # 1650
        assert data["max_height_ft"] == 35.0
        assert data["effective_height_ft"] == 35.0
        assert data["buildable_volume_cuft"] == 1650.0 * 35.0

        # No constraints triggered
        assert data["far_limited"] is False
        assert data["coverage_limited"] is False

    @pytest.mark.asyncio
    async def test_zero_setbacks(self, client: AsyncClient):
        """With zero setbacks, buildable area equals lot area."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 60,
                "lot_depth_ft": 120,
                "setback_front_ft": 0,
                "setback_side_ft": 0,
                "setback_rear_ft": 0,
                "max_height_ft": 40,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["buildable_width_ft"] == 60.0
        assert data["buildable_depth_ft"] == 120.0
        assert data["buildable_footprint_sqft"] == 7200.0
        assert data["lot_area_sqft"] == 7200.0

    @pytest.mark.asyncio
    async def test_setbacks_exceed_lot_width(self, client: AsyncClient):
        """Side setbacks exceed lot width — buildable width = 0."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 20,
                "lot_depth_ft": 100,
                "setback_front_ft": 0,
                "setback_side_ft": 15,
                "setback_rear_ft": 0,
                "max_height_ft": 35,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["buildable_width_ft"] == 0.0
        assert data["buildable_footprint_sqft"] == 0.0
        assert any("no buildable area" in n for n in data["notes"])

    @pytest.mark.asyncio
    async def test_far_limited_height(self, client: AsyncClient):
        """FAR constraint reduces effective height below max_height_ft."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 50,
                "lot_depth_ft": 100,
                "setback_front_ft": 0,
                "setback_side_ft": 0,
                "setback_rear_ft": 0,
                "max_height_ft": 100,
                "floor_area_ratio": 0.5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # lot_area = 5000, FAR = 0.5 → max_floor_area = 2500
        # buildable_footprint = 5000 (no setbacks)
        # far_max_height = 2500 / 5000 * 10 = 5.0
        assert data["far_limited"] is True
        assert data["effective_height_ft"] == pytest.approx(5.0)
        assert data["max_height_ft"] == 100.0
        assert any("FAR" in n for n in data["notes"])

    @pytest.mark.asyncio
    async def test_lot_coverage_constraint(self, client: AsyncClient):
        """Lot coverage constraint scales down buildable footprint."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 100,
                "lot_depth_ft": 100,
                "setback_front_ft": 0,
                "setback_side_ft": 0,
                "setback_rear_ft": 0,
                "max_height_ft": 35,
                "lot_coverage_pct": 50,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # lot_area = 10000, coverage limit = 50% → max footprint = 5000
        # buildable without constraint = 10000 > 5000, so coverage_limited
        assert data["coverage_limited"] is True
        assert data["effective_coverage_pct"] == 50.0
        assert data["buildable_footprint_sqft"] == pytest.approx(5000.0, rel=1e-2)
        assert any("lot coverage" in n for n in data["notes"])

    @pytest.mark.asyncio
    async def test_lot_polygon_vertices(self, client: AsyncClient):
        """Lot polygon should be 4 corners centered at origin."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={"lot_width_ft": 40, "lot_depth_ft": 80},
        )
        assert resp.status_code == 200
        data = resp.json()

        polygon = data["lot_polygon"]
        assert len(polygon) == 4

        # Corners should be ±20 in x, ±40 in y, z=0
        xs = sorted(v["x"] for v in polygon)
        ys = sorted(v["y"] for v in polygon)
        assert xs == [-20.0, -20.0, 20.0, 20.0]
        assert ys == [-40.0, -40.0, 40.0, 40.0]
        assert all(v["z"] == 0.0 for v in polygon)

    @pytest.mark.asyncio
    async def test_buildable_area_math(self, client: AsyncClient):
        """Verify buildable_footprint = buildable_width * buildable_depth."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={
                "lot_width_ft": 75,
                "lot_depth_ft": 150,
                "setback_front_ft": 30,
                "setback_side_ft": 10,
                "setback_rear_ft": 15,
                "max_height_ft": 45,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        expected_w = 75 - 2 * 10  # 55
        expected_d = 150 - 30 - 15  # 105
        assert data["buildable_width_ft"] == expected_w
        assert data["buildable_depth_ft"] == expected_d
        assert data["buildable_footprint_sqft"] == expected_w * expected_d
        assert data["buildable_volume_cuft"] == expected_w * expected_d * 45.0

    @pytest.mark.asyncio
    async def test_validation_rejects_zero_lot(self, client: AsyncClient):
        """lot_width_ft and lot_depth_ft must be > 0."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={"lot_width_ft": 0, "lot_depth_ft": 100},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_default_setbacks_are_zero(self, client: AsyncClient):
        """When setbacks are omitted, they default to 0."""
        resp = await client.post(
            "/api/v1/geometry/envelope",
            json={"lot_width_ft": 50, "lot_depth_ft": 100},
        )
        assert resp.status_code == 200
        data = resp.json()

        # No setbacks → buildable = lot
        assert data["buildable_width_ft"] == 50.0
        assert data["buildable_depth_ft"] == 100.0


class TestFloorPlanEndpoint:
    @pytest.mark.asyncio
    async def test_single_family_plan(self, client):
        resp = await client.post("/api/v1/geometry/floorplan", json={
            "buildable_width_ft": 40,
            "buildable_depth_ft": 80,
            "max_height_ft": 35,
            "max_units": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["template"] == "single_family"
        assert data["total_units"] == 1
        assert "<svg" in data["svg"]

    @pytest.mark.asyncio
    async def test_duplex_plan(self, client):
        resp = await client.post("/api/v1/geometry/floorplan", json={
            "buildable_width_ft": 40,
            "buildable_depth_ft": 80,
            "max_units": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["template"] == "duplex"
        assert data["total_units"] == 2

    @pytest.mark.asyncio
    async def test_multifamily_plan(self, client):
        resp = await client.post("/api/v1/geometry/floorplan", json={
            "buildable_width_ft": 60,
            "buildable_depth_ft": 100,
            "max_height_ft": 35,
            "max_units": 6,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["template"] == "small_multifamily"
        assert data["total_units"] <= 6
        assert data["stories"] >= 1

    @pytest.mark.asyncio
    async def test_floorplan_svg_output(self, client):
        resp = await client.post("/api/v1/geometry/floorplan", json={
            "buildable_width_ft": 40,
            "buildable_depth_ft": 80,
            "max_units": 1,
        })
        data = resp.json()
        assert data["svg"].startswith("<svg")
        assert "</svg>" in data["svg"]
