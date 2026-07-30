"""Tests for the UniversalProvider."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import PropertyRecord
from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.property.universal import (
    UniversalProvider,
    _build_property_record,
    _query_zoning,
)


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


async def test_palm_beach_zoning_prefers_fcode_over_description() -> None:
    dataset = DatasetInfo(
        dataset_id="pbc-zoning",
        name="Palm Beach zoning",
        url=(
            "https://maps.co.palm-beach.fl.us/arcgis/rest/services/"
            "OpenData/Planning_Open_Data/MapServer"
        ),
        layer_id=9,
        dataset_type="zoning",
        county="Palm Beach",
        state="FL",
        fields=["ZONING_DESC", "FNAME", "FCODE"],
    )
    features = [
        {
            "attributes": {
                "ZONING_DESC": "MIXED USE",
                "FNAME": "URBAN INFILL",
                "FCODE": "DDRI (city)",
            }
        }
    ]

    with patch(
        "plotlot.property.universal.spatial_query",
        new=AsyncMock(return_value=features),
    ):
        result = await _query_zoning(dataset, 26.3448, -80.0838)

    assert result == ("DDRI (city)", "MIXED USE")


class TestUniversalProvider:
    """Test the full provider lookup flow."""

    @pytest.fixture
    def provider(self):
        return UniversalProvider()

    async def test_requires_lat_lng(self, provider):
        """Should return None if lat/lng not provided."""
        result = await provider.lookup("123 Main St", "Test County")
        assert result is None

    async def test_registered_authoritative_provider_precedes_dynamic_discovery(self, provider):
        expected = PropertyRecord(
            folio="74434321060170150",
            address="623 4TH ST",
            county="Palm Beach",
        )
        authoritative_provider = AsyncMock()
        authoritative_provider.lookup.return_value = expected

        with (
            patch(
                "plotlot.property.universal.get_registered_provider",
                return_value=authoritative_provider,
            ),
            patch(
                "plotlot.property.universal.discover_datasets",
                new_callable=AsyncMock,
            ) as discover,
        ):
            result = await provider.lookup(
                "623 4TH ST, West Palm Beach, FL 33401",
                "Palm Beach",
                lat=26.717301,
                lng=-80.057865,
                state="FL",
            )

        assert result is expected
        authoritative_provider.lookup.assert_awaited_once()
        discover.assert_not_awaited()

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

    async def test_known_miami_sources_replace_stale_generic_cache(self, provider):
        stale_cache = CountyCache(
            county_key="miami-dade",
            state="FL",
            parcels_dataset=DatasetInfo(
                dataset_id="generic-parcels",
                name="Generic parcels",
                url="https://generic.example/FeatureServer",
                layer_id=1,
                dataset_type="parcels",
                county="Miami-Dade",
                state="FL",
                fields=["FOLIO", "PRIMARY_ZONE"],
            ),
            zoning_dataset=DatasetInfo(
                dataset_id="generic-zoning",
                name="Generic zoning",
                url="https://generic.example/Zoning/FeatureServer",
                layer_id=3,
                dataset_type="zoning",
                county="Miami-Dade",
                state="FL",
                fields=["ZONE"],
            ),
            field_mapping=FieldMapping(
                county_key="miami-dade",
                mappings={"FOLIO": "folio", "PRIMARY_ZONE": "zoning_code"},
            ),
        )
        known_parcels = DatasetInfo(
            dataset_id="known-parcels",
            name="Miami-Dade parcels",
            url="https://gis.miamidade.gov/arcgis/rest/services/MD_Communications/MapServer",
            layer_id=1,
            dataset_type="parcels",
            county="Miami-Dade",
            state="FL",
            fields=["FOLIO", "PRIMARY_ZONE", "DOR_CODE_CUR"],
        )
        known_zoning = DatasetInfo(
            dataset_id="known-zoning",
            name="Miami-Dade zoning",
            url=(
                "https://gisweb.miamidade.gov/arcgis/rest/services/"
                "LandManagement/MD_Zoning/MapServer"
            ),
            layer_id=2,
            dataset_type="zoning",
            county="Miami-Dade",
            state="FL",
            fields=["ZONE"],
        )
        refreshed_mapping = FieldMapping(
            county_key="miami-dade",
            mappings={
                "FOLIO": "folio",
                "PRIMARY_ZONE": "zoning_code",
                "DOR_CODE_CUR": "land_use_code",
            },
        )
        parcel_feature = {
            "attributes": {
                "FOLIO": "3421040000400",
                "PRIMARY_ZONE": "6500",
                "DOR_CODE_CUR": "6500",
            },
            "geometry": {},
        }

        with (
            patch(
                "plotlot.property.universal.get_county_cache",
                new=AsyncMock(return_value=stale_cache),
            ),
            patch(
                "plotlot.property.universal.get_field_mapping",
                new=AsyncMock(return_value=stale_cache.field_mapping),
            ),
            patch(
                "plotlot.property.universal.discover_datasets",
                new=AsyncMock(return_value=(known_parcels, known_zoning)),
            ) as discover,
            patch(
                "plotlot.property.universal.map_fields",
                new=AsyncMock(return_value=refreshed_mapping),
            ),
            patch(
                "plotlot.property.universal.save_county_cache",
                new=AsyncMock(),
            ) as save_cache,
            patch("plotlot.property.universal.save_field_mapping", new=AsyncMock()),
            patch(
                "plotlot.property.universal._query_parcel",
                new=AsyncMock(return_value=parcel_feature),
            ) as query_parcel,
            patch(
                "plotlot.property.universal._query_zoning",
                new=AsyncMock(return_value=("PCD", "Planned Corridor Development")),
            ) as query_zoning,
        ):
            result = await provider.lookup(
                "19501 NW 27th Ave",
                "Miami-Dade",
                lat=25.953,
                lng=-80.2449,
                state="FL",
            )

        assert result is not None
        assert result.zoning_code == "PCD"
        assert result.land_use_code == "6500"
        discover.assert_awaited_once()
        query_parcel.assert_awaited_once_with(
            known_parcels,
            "19501 NW 27th Ave",
            25.953,
            -80.2449,
            refreshed_mapping,
        )
        query_zoning.assert_awaited_once_with(known_zoning, 25.953, -80.2449)
        saved_cache = save_cache.await_args.args[0]
        assert saved_cache.parcels_dataset == known_parcels
        assert saved_cache.zoning_dataset == known_zoning
        assert saved_cache.field_mapping == refreshed_mapping

    async def test_known_zoning_unavailable_clears_parcel_zoning(self, provider):
        stale_cache = CountyCache(
            county_key="miami-dade",
            state="FL",
            parcels_dataset=DatasetInfo(
                dataset_id="generic-parcels",
                name="Generic parcels",
                url="https://generic.example/FeatureServer",
                layer_id=1,
                dataset_type="parcels",
                county="Miami-Dade",
                state="FL",
                fields=["PRIMARY_ZONE", "DOR_CODE_CUR"],
            ),
            field_mapping=FieldMapping(
                county_key="miami-dade",
                mappings={
                    "PRIMARY_ZONE": "zoning_code",
                    "DOR_CODE_CUR": "land_use_code",
                },
            ),
        )
        known_parcels = DatasetInfo(
            dataset_id="known-parcels",
            name="Miami-Dade parcels",
            url="https://gis.miamidade.gov/arcgis/rest/services/MD_Communications/MapServer",
            layer_id=1,
            dataset_type="parcels",
            county="Miami-Dade",
            state="FL",
            fields=["PRIMARY_ZONE", "DOR_CODE_CUR"],
        )
        refreshed_mapping = FieldMapping(
            county_key="miami-dade",
            mappings={
                "PRIMARY_ZONE": "zoning_code",
                "DOR_CODE_CUR": "land_use_code",
            },
        )

        with (
            patch(
                "plotlot.property.universal.get_county_cache",
                new=AsyncMock(return_value=stale_cache),
            ),
            patch(
                "plotlot.property.universal.get_field_mapping",
                new=AsyncMock(return_value=stale_cache.field_mapping),
            ),
            patch(
                "plotlot.property.universal.discover_datasets",
                new=AsyncMock(return_value=(known_parcels, None)),
            ),
            patch(
                "plotlot.property.universal.map_fields",
                new=AsyncMock(return_value=refreshed_mapping),
            ),
            patch(
                "plotlot.property.universal.save_county_cache",
                new=AsyncMock(),
            ) as save_cache,
            patch(
                "plotlot.property.universal.save_field_mapping",
                new=AsyncMock(),
            ) as save_mapping,
            patch(
                "plotlot.property.universal._query_parcel",
                new=AsyncMock(
                    return_value={
                        "attributes": {
                            "PRIMARY_ZONE": "6500",
                            "DOR_CODE_CUR": "6500",
                        },
                        "geometry": {},
                    }
                ),
            ),
        ):
            result = await provider.lookup(
                "19501 NW 27th Ave",
                "Miami-Dade",
                lat=25.953,
                lng=-80.2449,
                state="FL",
            )

        assert result is not None
        assert result.zoning_code == ""
        assert result.zoning_description == ""
        assert result.land_use_code == "6500"
        save_cache.assert_not_awaited()
        save_mapping.assert_not_awaited()
