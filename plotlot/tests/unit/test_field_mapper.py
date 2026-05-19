"""Tests for the field mapping engine."""

from plotlot.property.field_mapper import (
    ACRES_TO_SQFT,
    SQ_METERS_TO_SQFT,
    map_fields,
    map_fields_heuristic,
)


class TestHeuristicMapping:
    """Test keyword-based field mapping."""

    def test_miami_dade_fields(self):
        """MDC field names should map correctly."""
        fields = [
            "FOLIO",
            "TRUE_SITE_ADDR",
            "TRUE_SITE_CITY",
            "TRUE_OWNER1",
            "DOR_CODE_CUR",
            "DOR_DESC",
            "BEDROOM_COUNT",
            "BATHROOM_COUNT",
            "HALF_BATHROOM_COUNT",
            "FLOOR_COUNT",
            "UNIT_COUNT",
            "BUILDING_ACTUAL_AREA",
            "BUILDING_HEATED_AREA",
            "LOT_SIZE",
            "YEAR_BUILT",
            "ASSESSED_VAL_CUR",
            "PRICE_1",
            "DOS_1",
        ]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["FOLIO"] == "folio"
        assert mapping.mappings["TRUE_SITE_ADDR"] == "address"
        assert mapping.mappings["TRUE_OWNER1"] == "owner"
        assert mapping.mappings["DOR_CODE_CUR"] == "land_use_code"
        assert mapping.mappings["BEDROOM_COUNT"] == "bedrooms"
        assert mapping.mappings["BATHROOM_COUNT"] == "bathrooms"
        assert mapping.mappings["LOT_SIZE"] == "lot_size_sqft"
        assert mapping.mappings["YEAR_BUILT"] == "year_built"
        assert mapping.mappings["ASSESSED_VAL_CUR"] == "assessed_value"
        assert mapping.confidence >= 0.7

    def test_broward_fields(self):
        """Broward field names should map correctly."""
        fields = [
            "FOLIO_NUMBER",
            "SITUS_STREET_NUMBER",
            "SITUS_CITY",
            "NAME_LINE_1",
            "USE_CODE",
            "BLDG_YEAR_BUILT",
            "BLDG_ADJ_SQ_FOOTAGE",
            "UNDER_AIR_SQFT",
            "JUST_BUILDING_VALUE",
        ]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["FOLIO_NUMBER"] == "folio"
        assert mapping.mappings["NAME_LINE_1"] == "owner"
        assert mapping.mappings["USE_CODE"] == "land_use_code"
        assert mapping.mappings["BLDG_YEAR_BUILT"] == "year_built"

    def test_palm_beach_fields(self):
        """Palm Beach field names should map correctly."""
        fields = [
            "PARCEL_NUMBER",
            "SITE_ADDR_STR",
            "MUNICIPALITY",
            "OWNER_NAME1",
            "PROPERTY_USE",
            "YRBLT",
            "ACRES",
            "ASSESSED_VAL",
            "TOTAL_MARKET",
            "PRICE",
            "SALE_DATE",
        ]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["PARCEL_NUMBER"] == "folio"
        assert mapping.mappings["OWNER_NAME1"] == "owner"
        assert mapping.mappings["YRBLT"] == "year_built"
        assert mapping.mappings["ASSESSED_VAL"] == "assessed_value"
        assert mapping.mappings["TOTAL_MARKET"] == "market_value"

    def test_discovered_wake_style_fields(self):
        """Common discovered parcel fields should map without county-specific code."""
        fields = ["PARCEL_NUMBER", "SITEADR1", "SITECITY", "OWNER", "Acres", "TOTAMT"]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["PARCEL_NUMBER"] == "folio"
        assert mapping.mappings["SITEADR1"] == "address"
        assert mapping.mappings["SITECITY"] == "municipality"
        assert mapping.mappings["OWNER"] == "owner"
        assert mapping.mappings["TOTAMT"] == "assessed_value"
        assert mapping.unit_conversions["Acres"] == "acres_to_sqft"

    def test_raleigh_property_data_fields(self):
        """City-hosted property data fields should map to search result fields."""
        fields = [
            "PIN_NUM",
            "SITE_ADDRESS",
            "CITY_DECODE",
            "OWNER",
            "DEED_ACRES",
            "TOTAL_VALUE_ASSD",
            "TOTSALPRICE",
        ]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["PIN_NUM"] == "folio"
        assert mapping.mappings["SITE_ADDRESS"] == "address"
        assert mapping.mappings["CITY_DECODE"] == "municipality"
        assert mapping.mappings["DEED_ACRES"] == "lot_size_sqft"
        assert mapping.unit_conversions["DEED_ACRES"] == "acres_to_sqft"
        assert mapping.mappings["TOTAL_VALUE_ASSD"] == "assessed_value"
        assert mapping.mappings["TOTSALPRICE"] == "last_sale_price"

    def test_travis_property_data_fields(self):
        """Lowercase county parcel fields should map through normalized keywords."""
        fields = [
            "parcelid",
            "siteaddres",
            "ownernme1",
            "usecd",
            "usedscrp",
            "assessedac",
            "cntassdval",
            "bldgarea",
            "resflrarea",
            "resyrblt",
        ]
        mapping = map_fields_heuristic(fields)

        assert mapping.mappings["parcelid"] == "folio"
        assert mapping.mappings["siteaddres"] == "address"
        assert mapping.mappings["ownernme1"] == "owner"
        assert mapping.mappings["usecd"] == "land_use_code"
        assert mapping.mappings["usedscrp"] == "land_use_description"
        assert mapping.mappings["assessedac"] == "lot_size_sqft"
        assert mapping.unit_conversions["assessedac"] == "acres_to_sqft"
        assert mapping.mappings["cntassdval"] == "assessed_value"
        assert mapping.mappings["bldgarea"] == "building_area_sqft"
        assert mapping.mappings["resflrarea"] == "living_area_sqft"
        assert mapping.mappings["resyrblt"] == "year_built"

    def test_acres_conversion_detected(self):
        """Fields with ACRES should trigger unit conversion."""
        fields = ["PARCEL_ID", "ACRES", "OWNER"]
        mapping = map_fields_heuristic(fields)

        assert "ACRES" in mapping.unit_conversions
        assert mapping.unit_conversions["ACRES"] == "acres_to_sqft"

    def test_sq_meters_conversion_detected(self):
        """Fields with SQ_M should trigger unit conversion."""
        fields = ["PARCEL_ID", "LAND_SQ_M", "OWNER"]
        mapping = map_fields_heuristic(fields)

        # Should detect SQ_M in LAND_SQ_M
        converted = [k for k, v in mapping.unit_conversions.items() if v == "sq_meters_to_sqft"]
        assert len(converted) > 0

    def test_empty_fields(self):
        """Empty field list should return low confidence."""
        mapping = map_fields_heuristic([])
        assert mapping.confidence < 0.6
        assert len(mapping.mappings) == 0

    def test_unknown_fields(self):
        """Completely unknown field names should return low confidence."""
        fields = ["OBJECTID", "FID", "SHAPE", "GLOBALID"]
        mapping = map_fields_heuristic(fields)
        assert mapping.confidence < 0.6


class TestAsyncMapFields:
    """Test the async map_fields function."""

    async def test_high_confidence_skips_llm(self):
        """Good heuristic match should skip LLM call."""
        fields = [
            "FOLIO",
            "SITE_ADDR",
            "OWNER_NAME",
            "ZONE_CODE",
            "LOT_SIZE",
            "YEAR_BUILT",
            "ASSESSED_VAL",
            "BEDROOM_COUNT",
            "BATHROOM_COUNT",
            "BUILDING_AREA",
            "LIVING_AREA",
        ]
        mapping = await map_fields(fields, county="Test County")
        assert mapping.method == "heuristic"
        assert mapping.confidence >= 0.7
        assert mapping.county_key == "test county"


class TestConversionConstants:
    """Verify unit conversion constants."""

    def test_acres_to_sqft(self):
        assert ACRES_TO_SQFT == 43_560.0

    def test_sq_meters_to_sqft(self):
        assert abs(SQ_METERS_TO_SQFT - 10.764) < 0.001
