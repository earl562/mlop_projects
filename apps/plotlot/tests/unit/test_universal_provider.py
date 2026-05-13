"""Tests for the UniversalProvider."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.property.universal import UniversalProvider, _build_property_record


class TestBuildPropertyRecord:
    """Test PropertyRecord construction from ArcGIS features."""

    def test_basic_field_mapping(self):
        feature = {
            "attributes": {
                "FOLIO": "01-2345",
                "SITE_ADDR": "123 Main St",
                "OWNER_NAME": "John Doe",
                "LOT_SIZE": 7500.0,
                "YEAR_BUILT": 1985,
                "ASSESSED_VAL": 350000,
            },
            "geometry": {
                "rings": [[[-80.24, 25.93], [-80.24, 25.94], [-80.23, 25.94], [-80.24, 25.93]]]
            },
        }
        field_map = FieldMapping(
            county_key="test",
            mappings={
                "FOLIO": "folio",
                "SITE_ADDR": "address",
                "OWNER_NAME": "owner",
                "LOT_SIZE": "lot_size_sqft",
                "YEAR_BUILT": "year_built",
                "ASSESSED_VAL": "assessed_value",
            },
        )

        record = _build_property_record(feature, field_map, "Test County")

        assert record is not None
        assert record.folio == "01-2345"
        assert record.address == "123 Main St"
        assert record.owner == "John Doe"
        assert record.lot_size_sqft == 7500.0
        assert record.year_built == 1985
        assert record.assessed_value == 350000.0
        assert record.county == "Test County"
        assert record.parcel_geometry is not None

    def test_acres_conversion(self):
        feature = {
            "attributes": {"ACRES": 0.5},
            "geometry": {},
        }
        field_map = FieldMapping(
            county_key="test",
            mappings={"ACRES": "lot_size_sqft"},
            unit_conversions={"ACRES": "acres_to_sqft"},
        )

        record = _build_property_record(feature, field_map, "Test")
        assert record is not None
        assert abs(record.lot_size_sqft - 21780.0) < 1.0  # 0.5 * 43560

    def test_none_feature_returns_none(self):
        field_map = FieldMapping(county_key="test", mappings={})
        result = _build_property_record(None, field_map, "Test")
        assert result is None

    def test_zoning_override(self):
        feature = {"attributes": {"ZONE": "RS-1"}, "geometry": {}}
        field_map = FieldMapping(
            county_key="test",
            mappings={"ZONE": "zoning_code"},
        )

        record = _build_property_record(
            feature,
            field_map,
            "Test",
            zoning_code="RM-25",
            zoning_description="Residential Multifamily",
        )
        assert record is not None
        assert record.zoning_code == "RM-25"
        assert record.zoning_description == "Residential Multifamily"


class TestUniversalProvider:
    """Test the full provider lookup flow."""

    @pytest.fixture
    def provider(self):
        return UniversalProvider()

    async def test_requires_lat_lng(self, provider):
        """Should return None if lat/lng not provided."""
        result = await provider.lookup("123 Main St", "Test County")
        assert result is None

    async def test_cache_hit_skips_discovery(self, provider):
        """Cached county data should skip Hub discovery."""
        mock_cache = CountyCache(
            county_key="test",
            state="FL",
            parcels_dataset=DatasetInfo(
                dataset_id="abc",
                name="Parcels",
                url="https://example.com/FeatureServer",
                layer_id=0,
                dataset_type="parcels",
                county="Test",
                state="FL",
                fields=["FOLIO", "SITE_ADDR"],
            ),
            field_mapping=FieldMapping(
                county_key="test",
                mappings={"FOLIO": "folio", "SITE_ADDR": "address"},
            ),
        )

        mock_feature = {
            "attributes": {"FOLIO": "12345", "SITE_ADDR": "123 Main St"},
            "geometry": {},
        }

        with (
            patch(
                "plotlot.property.universal.get_county_cache",
                new_callable=AsyncMock,
                return_value=mock_cache,
            ),
            patch(
                "plotlot.property.universal.get_field_mapping",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "plotlot.property.universal.query_arcgis",
                new_callable=AsyncMock,
                return_value=[mock_feature],
            ),
            patch(
                "plotlot.property.universal.discover_datasets", new_callable=AsyncMock
            ) as mock_discover,
        ):
            result = await provider.lookup("123 Main St", "Test", lat=25.93, lng=-80.24, state="FL")

            assert result is not None
            assert result.folio == "12345"
            mock_discover.assert_not_called()

    async def test_cache_miss_triggers_discovery(self, provider):
        """Missing cache should trigger Hub discovery."""
        mock_ds = DatasetInfo(
            dataset_id="abc",
            name="Parcels",
            url="https://example.com/FeatureServer",
            layer_id=0,
            dataset_type="parcels",
            county="Test",
            state="TX",
            fields=["FOLIO", "SITE_ADDR"],
        )

        mock_feature = {
            "attributes": {"FOLIO": "99999", "SITE_ADDR": "456 Oak Ave"},
            "geometry": {},
        }

        with (
            patch(
                "plotlot.property.universal.get_county_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "plotlot.property.universal.get_field_mapping",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "plotlot.property.universal.discover_datasets",
                new_callable=AsyncMock,
                return_value=(mock_ds, None),
            ),
            patch("plotlot.property.universal.map_fields", new_callable=AsyncMock) as mock_map,
            patch("plotlot.property.universal.save_county_cache", new_callable=AsyncMock),
            patch("plotlot.property.universal.save_field_mapping", new_callable=AsyncMock),
            patch(
                "plotlot.property.universal.query_arcgis",
                new_callable=AsyncMock,
                return_value=[mock_feature],
            ),
        ):
            mock_map.return_value = FieldMapping(
                county_key="test",
                mappings={"FOLIO": "folio", "SITE_ADDR": "address"},
            )

            result = await provider.lookup("456 Oak Ave", "Test", lat=29.76, lng=-95.36, state="TX")

            assert result is not None
            assert result.folio == "99999"
