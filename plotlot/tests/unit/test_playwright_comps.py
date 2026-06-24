"""Tests for the SeleniumBase CDP-powered Zillow comps skill handler."""

from unittest.mock import patch

import pytest

from plotlot.pipeline.skills.playwright_comps import (
    _build_filter_state,
    _build_zillow_url,
    _extract_listings,
    _extract_sold_price,
    _parse_price,
    handle_fetch_zillow_comps,
    normalize_zillow_listing,
)
from plotlot.pipeline.skills.registry import get_handler


def test_zillow_comps_registered() -> None:
    handler = get_handler("fetch_zillow_comps")
    assert handler is handle_fetch_zillow_comps


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (525000, 525000),
        (525000.0, 525000),
        ("$525,000", 525000),
        ("$4,700/mo", 4700),
        ("$30,000/mo", 30000),
        ("not a price", 0),
        (None, 0),
        ("", 0),
    ],
)
def test_parse_price(raw, expected: int) -> None:
    assert _parse_price(raw) == expected


def test_extract_sold_price_from_hdp() -> None:
    raw = {"price": 0, "hdpData": {"homeInfo": {"lastSoldPrice": 450000}}}
    hdp = raw["hdpData"]["homeInfo"]
    assert _extract_sold_price(raw, hdp) == 450000


def test_extract_sold_price_from_raw() -> None:
    raw = {"price": 525000}
    assert _extract_sold_price(raw, {}) == 525000


def test_extract_sold_price_zero() -> None:
    raw = {"price": 0}
    assert _extract_sold_price(raw, {}) == 0


# ---------------------------------------------------------------------------
# Filter state construction (Kleyman deal-path scenarios)
# ---------------------------------------------------------------------------


def test_filter_state_rental_has_for_rent() -> None:
    fs = _build_filter_state("rental")
    assert fs["isForRent"]["value"] is True
    assert fs["isForSaleByAgent"]["value"] is False


def test_filter_state_land_has_lot_land() -> None:
    fs = _build_filter_state("land")
    assert fs["isLotLand"]["value"] is True
    assert fs["isSingleFamily"]["value"] is False
    assert fs["isRecentlySold"]["value"] is True
    assert fs["doz"]["value"] == "12m"


def test_filter_state_land_with_acreage() -> None:
    fs = _build_filter_state("land", min_acres=1, max_acres=10)
    assert fs["lotSize"]["min"] == 1
    assert fs["lotSize"]["max"] == 10
    assert fs["lotSize"]["units"] == "acres"


def test_filter_state_new_build_has_built_range() -> None:
    fs = _build_filter_state("new_build")
    assert fs["isSingleFamily"]["value"] is True
    assert fs["isRecentlySold"]["value"] is True
    assert "built" in fs
    assert fs["built"]["max"] >= fs["built"]["min"]


def test_filter_state_renovated_has_keyword() -> None:
    fs = _build_filter_state("renovated")
    assert fs["keywords"]["value"] == "renovated"
    assert fs["isRecentlySold"]["value"] is True


def test_filter_state_small_mf_has_multi_family() -> None:
    fs = _build_filter_state("small_mf")
    assert fs["isMultiFamily"]["value"] is True
    assert fs["isLotLand"]["value"] is False
    assert fs["isRecentlySold"]["value"] is True


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def test_build_zillow_url_contains_zip() -> None:
    fs = _build_filter_state("rental")
    url = _build_zillow_url("33165", fs)
    assert "33165_rb" in url
    assert "searchQueryState" in url


def test_build_zillow_url_encodes_json() -> None:
    fs = _build_filter_state("rental")
    url = _build_zillow_url("33165", fs)
    # URL should be properly encoded — no raw braces
    assert "{" not in url
    assert "}" not in url


# ---------------------------------------------------------------------------
# __NEXT_DATA__ extraction
# ---------------------------------------------------------------------------


def _make_next_data(cat1=None, cat2=None) -> dict:
    return {
        "props": {
            "pageProps": {
                "searchPageState": {
                    "cat1": {"searchResults": {"listResults": cat1 or []}},
                    "cat2": {"searchResults": {"listResults": cat2 or []}},
                }
            }
        }
    }


def test_extract_sold_prefers_cat2() -> None:
    nd = _make_next_data(cat1=[{"address": "a1"}], cat2=[{"address": "s1"}, {"address": "s2"}])
    result = _extract_listings(nd, "land")
    assert len(result) == 2
    assert result[0]["address"] == "s1"


def test_extract_sold_falls_back_to_cat1() -> None:
    nd = _make_next_data(cat1=[{"address": "a1"}, {"address": "a2"}], cat2=[])
    result = _extract_listings(nd, "new_build")
    assert len(result) == 2


def test_extract_rental_prefers_cat1() -> None:
    nd = _make_next_data(cat1=[{"address": "r1"}], cat2=[{"address": "s1"}])
    result = _extract_listings(nd, "rental")
    assert len(result) == 1
    assert result[0]["address"] == "r1"


def test_extract_missing_search_state() -> None:
    assert _extract_listings({}, "rental") == []


def test_extract_missing_cat() -> None:
    nd = {"props": {"pageProps": {"searchPageState": {}}}}
    assert _extract_listings(nd, "rental") == []


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _make_raw_listing(**overrides) -> dict:
    base = {
        "zpid": 12345678,
        "address": "123 Main St, Miami, FL 33169",
        "price": 525000,
        "hdpData": {
            "homeInfo": {
                "bedrooms": 3,
                "bathrooms": 2.0,
                "livingArea": 1850,
                "lotAreaValue": 7500,
                "yearBuilt": 2005,
                "homeType": "SINGLE_FAMILY",
            }
        },
        "detailUrl": "/homedetails/123-Main-St/12345678_zpid/",
        "latLong": {"latitude": 25.76, "longitude": -80.19},
        "variableData": {"sold_date": "2025-03-15"},
    }
    base.update(overrides)
    return base


def test_normalize_rental() -> None:
    raw = _make_raw_listing(price="$2,500/mo")
    n = normalize_zillow_listing(raw, "rental")
    assert n["price"] == 2500
    assert n["bedrooms"] == 3
    assert n["sqft"] == 1850
    assert n["source"] == "zillow"
    assert n["listing_type"] == "rental"


def test_normalize_sold_uses_last_sold_price() -> None:
    raw = _make_raw_listing(
        price=0,
        hdpData={"homeInfo": {"lastSoldPrice": 450000, "bedrooms": 2}},
    )
    n = normalize_zillow_listing(raw, "land")
    assert n["price"] == 450000
    assert n["bedrooms"] == 2


def test_normalize_minimal() -> None:
    raw = {"zpid": 1, "address": "Test", "price": 0}
    n = normalize_zillow_listing(raw, "rental")
    assert n["source_id"] == "1"
    assert n["price"] == 0
    assert n["bedrooms"] is None


def test_normalize_none_subobjects() -> None:
    raw = {"zpid": 1, "address": "", "price": 0, "hdpData": None, "latLong": None, "variableData": None}
    n = normalize_zillow_listing(raw, "for_sale")
    assert n["bedrooms"] is None
    assert n["latitude"] is None


# ---------------------------------------------------------------------------
# Handler — input validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_no_address() -> None:
    result = await handle_fetch_zillow_comps({})
    assert result.output_json["count"] == 0
    assert result.output_json["error"] == "No address provided"


@pytest.mark.asyncio
async def test_handler_no_zip_code() -> None:
    result = await handle_fetch_zillow_comps({"address": "123 Main St, Miami, FL"})
    assert result.output_json["count"] == 0
    assert "No ZIP code" in result.output_json["error"]


@pytest.mark.asyncio
async def test_handler_unknown_scenario_defaults_to_rental() -> None:
    with patch("plotlot.pipeline.skills.playwright_comps.run_stealth_fetch") as mock_fetch:
        mock_fetch.return_value = {"data": {"comparables": [], "count": 0}, "cookies": [], "captcha_solved": False, "title": "test"}
        await handle_fetch_zillow_comps({"address": "123 Main St, Miami, FL 33169", "listing_type": "unknown"})
        args = mock_fetch.call_args
        url = args[0][0]
        assert "33165" not in url  # 33169 is the zip


@pytest.mark.asyncio
async def test_handler_calls_stealth_fetch() -> None:
    with patch("plotlot.pipeline.skills.playwright_comps.run_stealth_fetch") as mock_fetch:
        mock_fetch.return_value = {
            "data": {"comparables": [{"address": "test", "price": 1000}], "count": 1},
            "cookies": [],
            "captcha_solved": False,
            "title": "Test Page",
        }
        result = await handle_fetch_zillow_comps({
            "address": "2914 SW 103rd Ct, Miami, FL 33165",
            "listing_type": "rental",
            "max_results": 5,
        })
        assert mock_fetch.called
        assert result.output_json["count"] == 1
        assert result.output_json["comparables"][0]["address"] == "test"


@pytest.mark.asyncio
async def test_handler_handles_stealth_error() -> None:
    with patch("plotlot.pipeline.skills.playwright_comps.run_stealth_fetch") as mock_fetch:
        mock_fetch.return_value = {"data": {}, "cookies": [], "captcha_solved": False, "error": "CAPTCHA could not be solved"}
        result = await handle_fetch_zillow_comps({
            "address": "2914 SW 103rd Ct, Miami, FL 33165",
            "listing_type": "rental",
        })
        assert result.output_json["count"] == 0
        assert "CAPTCHA" in result.output_json["error"]
