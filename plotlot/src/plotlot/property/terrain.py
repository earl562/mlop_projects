"""Parcel terrain analysis from the USGS 3DEP elevation model.

Florida parcels are flat, so buildable area is effectively lot area and a unit
count is just ``density x acres``. San Diego parcels are frequently not, and the
codes respond to that: San Diego Municipal Code §113.0103 defines

    "Steep hillsides means all lands that have a slope with a natural gradient of
    25 percent ... or greater and a minimum elevation differential of 50 feet, or
    a natural gradient of 200 percent ... or greater and a minimum elevation
    differential of 10 feet."

Steep hillsides are Environmentally Sensitive Lands (SDMC §143.0110), which caps
encroachment and pushes the project onto a discretionary permit. Carlsbad reaches
the same place from another direction, sizing coverage off "net developable
acreage" rather than lot area.

The consequence for us is narrow and important: on a sloped parcel, applying
density to *gross* lot area overstates yield. This module measures the slope so
that overstatement can be detected and labelled. It deliberately does **not**
compute an authoritative buildable area — that requires the jurisdiction's own
slope analysis on survey-grade topography, and inventing one would produce a
confident wrong number, which is worse than a flagged uncertain one.

Everything here is best-effort: any failure returns None and the caller behaves
exactly as it did before.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# USGS 3DEP dynamic image service. getSamples accepts a multipoint and returns
# every elevation in one round trip (~2s for 64 points), where the per-point
# EPQS endpoint costs 1-2s *each* and cannot be used per-parcel.
_3DEP_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples"
)
_TIMEOUT_S = 20.0

# 10x10 = 100 points still returns in ~2s in one request.
_GRID = 10
_MAX_SAMPLES = 144

# The ordinance's 50 ft differential describes the *slope feature*, not the
# parcel. A typical residential lot is 20-40 m across and will almost never span
# 50 ft of relief even when it sits squarely on a steep hillside, so measuring
# relief inside the parcel alone systematically under-detects. Sampling is
# therefore buffered outward; slope statistics stay parcel-scoped, while the
# elevation differential is read across the buffered area.
_BUFFER_M = 60.0

METERS_PER_FOOT = 0.3048
_EARTH_M_PER_DEG_LAT = 111_320.0

# SDMC §113.0103. Two limbs, either of which makes land a "steep hillside".
STEEP_GRADIENT_PCT = 25.0
STEEP_ELEVATION_DIFF_FT = 50.0
VERY_STEEP_GRADIENT_PCT = 200.0
VERY_STEEP_ELEVATION_DIFF_FT = 10.0

# Trust gate, distinct from the ordinance test above. This does not assert that
# any hillside regulation applies — it asserts that "buildable area == lot area"
# has stopped being a safe assumption, so a density-times-gross-acres unit count
# must not be presented as firm. Deliberately lower than the ordinance test,
# because being wrong here should cost a caveat, not a wrong number.
SLOPE_CONSTRAINED_MEAN_PCT = 15.0
SLOPE_CONSTRAINED_STEEP_FRACTION = 0.25


@dataclass
class TerrainAnalysis:
    """Measured slope characteristics of a parcel.

    ``steep_fraction`` is the share of sampled points whose local gradient meets
    the steep threshold. It is an *estimate* of how much of the parcel is steep,
    not a survey, and must never be presented as a buildable-area determination.
    """

    mean_slope_pct: float
    max_slope_pct: float
    elevation_min_ft: float
    elevation_max_ft: float
    #: Relief across the buffered slope feature, not merely inside the parcel.
    elevation_differential_ft: float
    steep_fraction: float
    sample_count: int
    #: Meets the jurisdiction's formal steep-hillside definition.
    is_steep_hillside: bool
    #: Gross lot area is no longer a safe proxy for buildable area. Broader than
    #: ``is_steep_hillside`` — this is what gates whether a unit count is firm.
    slope_constrained: bool
    #: Which limb of the definition was met, for citation in the report.
    steep_basis: str = ""
    source: str = "USGS 3DEP"
    resolution_note: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def steep_pct(self) -> int:
        return round(self.steep_fraction * 100)

    def summary(self) -> str:
        """One-line description safe to echo verbatim into a report."""
        return (
            f"{self.mean_slope_pct:.0f}% average slope, {self.max_slope_pct:.0f}% maximum; "
            f"{self.steep_pct}% of the parcel at or above {STEEP_GRADIENT_PCT:.0f}% gradient; "
            f"{self.elevation_differential_ft:.0f} ft of relief across the slope "
            f"({self.source}, {self.resolution_note})"
        )

    def yield_caveat(self) -> str:
        """Why a gross-area unit count cannot be trusted on this parcel."""
        if not self.slope_constrained:
            return ""
        if self.is_steep_hillside:
            return (
                f"Parcel meets the steep-hillside definition ({self.steep_basis}). "
                "Steep hillsides are Environmentally Sensitive Lands: encroachment is "
                "restricted and a discretionary permit is likely required. The unit "
                "count below applies density to gross lot area and is therefore an "
                "upper bound, not an entitlement."
            )
        return (
            f"About {self.steep_pct}% of this parcel sits at or above a "
            f"{STEEP_GRADIENT_PCT:.0f}% gradient ({self.mean_slope_pct:.0f}% average). "
            "Buildable area is likely smaller than lot area, so the unit count below "
            "applies density to gross lot area and is an upper bound."
        )


def _polygon_bbox(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    lngs = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    return min(lngs), min(lats), max(lngs), max(lats)


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting test. Avoids a shapely dependency for one predicate."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


async def _fetch_elevations(
    points: list[list[float]], client: httpx.AsyncClient | None = None
) -> list[float | None]:
    """Sample 3DEP at each WGS84 point. Returns metres, None where NoData."""
    geometry = {"points": points, "spatialReference": {"wkid": 4326}}
    params = {
        "geometry": json.dumps(geometry),
        "geometryType": "esriGeometryMultipoint",
        "returnFirstValueOnly": "true",
        "sampleCount": len(points),
        "f": "json",
    }

    owns = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT_S)
    try:
        resp = await client.get(_3DEP_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("terrain_fetch_failed points=%d error=%s", len(points), exc)
        return []
    finally:
        if owns:
            await client.aclose()

    if payload.get("error"):
        logger.warning("terrain_service_error error=%s", payload["error"])
        return []

    # Samples come back keyed by locationId, not necessarily in request order.
    values: list[float | None] = [None] * len(points)
    for sample in payload.get("samples", []):
        try:
            idx = int(sample.get("locationId", -1))
            raw = sample.get("value")
            if 0 <= idx < len(values) and raw not in (None, "", "NoData"):
                values[idx] = float(raw)
        except (TypeError, ValueError):
            continue
    return values


async def analyze_terrain(
    parcel_geometry: list[list[float]] | None,
    *,
    client: httpx.AsyncClient | None = None,
) -> TerrainAnalysis | None:
    """Measure a parcel's slope from 3DEP. Returns None when unavailable.

    Samples a ``_GRID``x``_GRID`` grid across the parcel's bounding box (10x10
    at the current setting), computes the slope
    field by central differences, then restricts the statistics to the points
    that actually fall inside the parcel polygon. Sampling the full box rather
    than only interior points keeps the gradient well defined at the edges.
    """
    if not parcel_geometry or len(parcel_geometry) < 3:
        return None

    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a hard dependency in practice
        logger.warning("terrain_numpy_missing")
        return None

    min_lng, min_lat, max_lng, max_lat = _polygon_bbox(parcel_geometry)
    if max_lng <= min_lng or max_lat <= min_lat:
        return None

    mid_lat = (min_lat + max_lat) / 2.0
    m_per_deg_lat = _EARTH_M_PER_DEG_LAT
    m_per_deg_lng = _EARTH_M_PER_DEG_LAT * math.cos(math.radians(mid_lat))
    if m_per_deg_lng <= 0:
        return None

    # Buffer outward so the elevation differential describes the slope feature.
    buf_lng = _BUFFER_M / m_per_deg_lng
    buf_lat = _BUFFER_M / m_per_deg_lat
    box_min_lng, box_max_lng = min_lng - buf_lng, max_lng + buf_lng
    box_min_lat, box_max_lat = min_lat - buf_lat, max_lat + buf_lat

    lngs = [box_min_lng + (box_max_lng - box_min_lng) * i / (_GRID - 1) for i in range(_GRID)]
    lats = [box_min_lat + (box_max_lat - box_min_lat) * j / (_GRID - 1) for j in range(_GRID)]

    points = [[lng, lat] for lat in lats for lng in lngs]
    if len(points) > _MAX_SAMPLES:
        return None

    elevations = await _fetch_elevations(points, client=client)
    if not elevations or sum(v is not None for v in elevations) < 4:
        return None

    # NaN-fill so gradients stay defined; masked out of the statistics below.
    grid = np.array(
        [
            [np.nan if v is None else v for v in elevations[r * _GRID : (r + 1) * _GRID]]
            for r in range(_GRID)
        ],
        dtype=float,
    )
    if np.all(np.isnan(grid)):
        return None
    grid = np.where(np.isnan(grid), np.nanmean(grid), grid)

    step_x_m = (box_max_lng - box_min_lng) * m_per_deg_lng / (_GRID - 1)
    step_y_m = (box_max_lat - box_min_lat) * m_per_deg_lat / (_GRID - 1)
    if step_x_m <= 0 or step_y_m <= 0:
        return None

    dz_dy, dz_dx = np.gradient(grid, step_y_m, step_x_m)
    slope_pct = np.hypot(dz_dx, dz_dy) * 100.0

    inside = np.array(
        [[_point_in_polygon(lng, lat, parcel_geometry) for lng in lngs] for lat in lats],
        dtype=bool,
    )
    # A small parcel can miss every grid node; fall back to the parcel's own
    # bounding box rather than reporting nothing, and say so.
    notes: list[str] = []
    if inside.sum() < 3:
        inside = np.array(
            [
                [min_lng <= lng <= max_lng and min_lat <= lat <= max_lat for lng in lngs]
                for lat in lats
            ],
            dtype=bool,
        )
        notes.append(
            "Parcel smaller than the sampling grid — slope measured over its bounding box."
        )
    if inside.sum() < 3:
        inside = np.ones_like(inside, dtype=bool)
        notes.append("Slope measured over the buffered sample area.")

    # Slope describes the parcel; relief describes the surrounding slope feature,
    # which is what the ordinance's elevation-differential limb refers to.
    slopes = slope_pct[inside]
    elevation_min_ft = float(np.min(grid)) / METERS_PER_FOOT
    elevation_max_ft = float(np.max(grid)) / METERS_PER_FOOT
    differential_ft = elevation_max_ft - elevation_min_ft

    mean_slope = float(np.mean(slopes))
    max_slope = float(np.max(slopes))
    steep_fraction = float(np.mean(slopes >= STEEP_GRADIENT_PCT))

    steep_basis = ""
    if mean_slope >= VERY_STEEP_GRADIENT_PCT and differential_ft >= VERY_STEEP_ELEVATION_DIFF_FT:
        steep_basis = (
            f"{mean_slope:.0f}% average gradient with {differential_ft:.0f} ft of relief "
            f"(>= {VERY_STEEP_GRADIENT_PCT:.0f}% and >= {VERY_STEEP_ELEVATION_DIFF_FT:.0f} ft)"
        )
    elif mean_slope >= STEEP_GRADIENT_PCT and differential_ft >= STEEP_ELEVATION_DIFF_FT:
        steep_basis = (
            f"{mean_slope:.0f}% average gradient with {differential_ft:.0f} ft of relief "
            f"(>= {STEEP_GRADIENT_PCT:.0f}% and >= {STEEP_ELEVATION_DIFF_FT:.0f} ft)"
        )

    slope_constrained = (
        bool(steep_basis)
        or mean_slope >= SLOPE_CONSTRAINED_MEAN_PCT
        or steep_fraction >= SLOPE_CONSTRAINED_STEEP_FRACTION
    )

    return TerrainAnalysis(
        mean_slope_pct=round(mean_slope, 1),
        max_slope_pct=round(max_slope, 1),
        elevation_min_ft=round(elevation_min_ft, 1),
        elevation_max_ft=round(elevation_max_ft, 1),
        elevation_differential_ft=round(differential_ft, 1),
        steep_fraction=round(steep_fraction, 3),
        sample_count=int(inside.sum()),
        is_steep_hillside=bool(steep_basis),
        slope_constrained=slope_constrained,
        steep_basis=steep_basis,
        resolution_note=f"{_GRID}x{_GRID} grid, ~{step_x_m:.0f} m spacing",
        notes=notes,
    )
