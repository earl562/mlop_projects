from __future__ import annotations

from unittest.mock import AsyncMock, patch

from plotlot.core.types import PropertyRecord


class TestOpenDataOnlyComparableBehavior:
    async def test_no_arcgis_dataset_returns_open_data_only_notes(self):
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19, lot_size_sqft=7710.0)

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset",
                new=AsyncMock(return_value=None),
            ),
        ):
            out = await find_comparables(subject, state="CA")

        assert out.adv_source != "comps"
        assert out.adv_per_unit is None
        assert out.sales_source_type == ""
        assert out.exit_comp_source_type == ""
        assert any("No sales dataset found" in note for note in out.notes)
        assert any("Open-data-only comps path" in note for note in out.notes)

    async def test_arcgis_land_only_path_keeps_exit_signal_empty(self):
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
        )

        features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "494233281490",
                    "SALE_AMOUNT": 425000,
                    "SALE_DATE": "2026-03-15",
                    "SHAPE.STArea()": 9800.0,
                },
                "geometry": {
                    "rings": [
                        [[-80.16, 26.145], [-80.159, 26.145], [-80.159, 26.146], [-80.16, 26.145]]
                    ]
                },
            }
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        ["FOLIO_NUMBER", "SALE_AMOUNT", "SALE_DATE", "SHAPE.STArea()"],
                    )
                ),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch(
                "plotlot.pipeline.comps._enrich_broward_sales_features",
                new=AsyncMock(return_value=features),
            ),
        ):
            out = await find_comparables(subject, state="FL")

        assert out.adv_source != "comps"
        assert out.adv_per_unit is None
        assert len(out.unit_comparables) == 0
        assert len(out.comparables) == 1
        assert any("No nearby improved sales found" in note for note in out.notes)
