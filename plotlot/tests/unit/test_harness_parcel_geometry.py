from __future__ import annotations

import pytest

from plotlot.harness.parcel_geometry import derive_lot_dimensions_from_parcel_geometry


def test_derive_lot_dimensions_from_parcel_geometry_uses_bounding_box_spans() -> None:
    ring = [
        [0.0, 0.0],
        [50.0 / 364000.0, 0.0],
        [50.0 / 364000.0, 120.0 / 364000.0],
        [0.0, 120.0 / 364000.0],
        [0.0, 0.0],
    ]

    frontage_ft, depth_ft = derive_lot_dimensions_from_parcel_geometry(ring)

    assert frontage_ft == pytest.approx(50.0, abs=0.05)
    assert depth_ft == pytest.approx(120.0, abs=0.05)


def test_derive_lot_dimensions_from_parcel_geometry_rejects_incomplete_rings() -> None:
    assert derive_lot_dimensions_from_parcel_geometry(None) == (None, None)
    assert derive_lot_dimensions_from_parcel_geometry([[0.0, 0.0], [1.0, 1.0]]) == (None, None)
