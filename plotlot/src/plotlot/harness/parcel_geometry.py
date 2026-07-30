from __future__ import annotations

import math


_FEET_PER_DEGREE_LAT = 364_000.0


def derive_lot_dimensions_from_parcel_geometry(
    parcel_geometry: object,
) -> tuple[float | None, float | None]:
    if not isinstance(parcel_geometry, list) or len(parcel_geometry) < 3:
        return None, None

    points: list[tuple[float, float]] = []
    for point in parcel_geometry:
        if not isinstance(point, list | tuple) or len(point) < 2:
            continue
        lng_raw, lat_raw = point[0], point[1]
        if not isinstance(lng_raw, int | float) or not isinstance(lat_raw, int | float):
            continue
        points.append((float(lng_raw), float(lat_raw)))

    if len(points) < 3:
        return None, None

    lng_values = [point[0] for point in points]
    lat_values = [point[1] for point in points]
    center_lat = sum(lat_values) / len(lat_values)
    lat_span_ft = (max(lat_values) - min(lat_values)) * _FEET_PER_DEGREE_LAT
    lng_scale = _FEET_PER_DEGREE_LAT * math.cos(math.radians(center_lat))
    lng_span_ft = (max(lng_values) - min(lng_values)) * abs(lng_scale)

    width_ft = min(lat_span_ft, lng_span_ft)
    depth_ft = max(lat_span_ft, lng_span_ft)
    if width_ft <= 0 or depth_ft <= 0:
        return None, None
    return round(width_ft, 2), round(depth_ft, 2)
