"""Tests for the playwright-comps skill handler."""

import pytest

from plotlot.pipeline.skills.playwright_comps import (
    _address_to_slug,
    _build_zillow_url,
    _extract_listings,
    handle_fetch_zillow_comps,
    normalize_zillow_listing,
)
from plotlot.pipeline.skills.registry import get_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_zillow_comps_registered() -> None:
    """The handler is registered under 'fetch_zillow_comps' in the skill registry."""
    handler = get_handler("fetch_zillow_comps")
    assert handler is handle_fetch_zillow_comps


# ---------------------------------------------------------------------------
# Address → slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address,expected",
    [
        ("123 Main St, Miami, FL 33169", "123-main-st-miami-fl-33169"),
        ("1234 North West 5th Avenue, Los Angeles, CA 90001", "1234-north-west-5th-avenue-los-angeles-ca-90001"),
        ("  leading and trailing  ", "leading-and-trailing"),
        ("multiple---dashes", "multiple-dashes"),
        ("", ""),
    ],
)
def test_address_to_slug(address: str, expected: str) -> None:
    assert _address_to_slug(address) == expected


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def test_build_zillow_url_sold() -> None:
    url = _build_zillow_url("123-main-st-miami-fl-33169", "sold")
    assert url == "https://www.zillow.com/homes/123-main-st-miami-fl-33169_rb/sold/"


def test_build_zillow_url_rental() -> None:
    url = _build_zillow_url("123-main-st-miami-fl-33169", "rental")
    assert url == "https://www.zillow.com/homes/123-main-st-miami-fl-33169_rb/rental/"


def test_build_zillow_url_for_sale() -> None:
    url = _build_zillow_url("123-main-st-miami-fl-33169", "for_sale")
    assert url == "https://www.zillow.com/homes/123-main-st-miami-fl-33169_rb/"


# ---------------------------------------------------------------------------
# __NEXT_DATA__ extraction
# ---------------------------------------------------------------------------


def _make_next_data(cat1_listings: list[dict] | None = None, cat2_listings: list[dict] | None = None) -> dict:
    """Build a minimal __NEXT_DATA__ payload."""
    return {
        "props": {
            "pageProps": {
                "searchPageState": {
                    "cat1": {
                        "searchResults": {
                            "listResults": cat1_listings or [],
                        }
                    },
                    "cat2": {
                        "searchResults": {
                            "listResults": cat2_listings or [],
                        }
                    },
                }
            }
        }
    }


def test_extract_sold_listings() -> None:
    next_data = _make_next_data(
        cat1_listings=[{"address": "for-sale-1"}],
        cat2_listings=[{"address": "sold-1"}, {"address": "sold-2"}],
    )
    result = _extract_listings(next_data, "sold")
    assert len(result) == 2
    assert result[0]["address"] == "sold-1"


def test_extract_rental_listings() -> None:
    next_data = _make_next_data(
        cat1_listings=[{"address": "rental-1"}],
        cat2_listings=[{"address": "sold-1"}],
    )
    result = _extract_listings(next_data, "rental")
    assert len(result) == 1
    assert result[0]["address"] == "rental-1"


def test_extract_for_sale_listings() -> None:
    next_data = _make_next_data(
        cat1_listings=[{"address": "for-sale-1"}],
        cat2_listings=[{"address": "sold-1"}],
    )
    result = _extract_listings(next_data, "for_sale")
    assert len(result) == 1
    assert result[0]["address"] == "for-sale-1"


def test_extract_missing_search_state() -> None:
    result = _extract_listings({}, "sold")
    assert result == []


def test_extract_missing_cat() -> None:
    next_data = {"props": {"pageProps": {"searchPageState": {}}}}
    result = _extract_listings(next_data, "sold")
    assert result == []


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalize_zillow_listing_sold() -> None:
    raw = {
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
        "detailUrl": "/homedetails/123-Main-St-Miami-FL-33169/12345678_zpid/",
        "latLong": {"latitude": 25.7617, "longitude": -80.1918},
        "variableData": {"sold_date": "2025-03-15"},
    }

    normalized = normalize_zillow_listing(raw, "sold")

    assert normalized["source_id"] == "12345678"
    assert normalized["address"] == "123 Main St, Miami, FL 33169"
    assert normalized["price"] == 525000
    assert normalized["bedrooms"] == 3
    assert normalized["bathrooms"] == 2.0
    assert normalized["sqft"] == 1850
    assert normalized["lot_sqft"] == 7500
    assert normalized["year_built"] == 2005
    assert normalized["property_type"] == "SINGLE_FAMILY"
    assert normalized["sold_date"] == "2025-03-15"
    assert normalized["latitude"] == 25.7617
    assert normalized["longitude"] == -80.1918
    assert normalized["source_url"] == "/homedetails/123-Main-St-Miami-FL-33169/12345678_zpid/"
    assert normalized["source"] == "zillow"
    assert normalized["listing_type"] == "sold"


def test_normalize_zillow_listing_minimal() -> None:
    """Minimal raw listing — all optional fields should return None/0/'' as defaults."""
    raw = {
        "zpid": 99999,
        "address": "Minimal St",
        "price": 0,
    }

    normalized = normalize_zillow_listing(raw, "rental")

    assert normalized["source_id"] == "99999"
    assert normalized["address"] == "Minimal St"
    assert normalized["price"] == 0
    assert normalized["bedrooms"] is None
    assert normalized["bathrooms"] is None
    assert normalized["sqft"] is None
    assert normalized["lot_sqft"] is None
    assert normalized["year_built"] is None
    assert normalized["property_type"] is None
    assert normalized["sold_date"] is None
    assert normalized["latitude"] is None
    assert normalized["longitude"] is None
    assert normalized["source_url"] == ""
    assert normalized["source"] == "zillow"
    assert normalized["listing_type"] == "rental"


def test_normalize_zillow_listing_none_sub_objects() -> None:
    """Gracefully handles None for hdpData, latLong, variableData."""
    raw = {
        "zpid": 1,
        "address": "",
        "price": 0,
        "hdpData": None,
        "latLong": None,
        "variableData": None,
    }

    normalized = normalize_zillow_listing(raw, "for_sale")
    assert normalized["bedrooms"] is None
    assert normalized["latitude"] is None
    assert normalized["sold_date"] is None


# ---------------------------------------------------------------------------
# Handler — missing input / missing playwright
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_no_address() -> None:
    """Handler should return an empty result (not crash) when address is missing."""
    result = await handle_fetch_zillow_comps({})
    assert result.output_json["count"] == 0
    assert result.output_json["source"] == "zillow"
    assert result.output_json["error"] == "No address provided"


@pytest.mark.asyncio
async def test_handler_missing_playwright(monkeypatch) -> None:
    """Handler returns an error when the playwright package is not installed."""
    import plotlot.pipeline.skills.playwright_comps as mod

    monkeypatch.setattr(mod, "async_playwright", None)
    result = await mod.handle_fetch_zillow_comps({"address": "123 Main St, Miami, FL 33169"})
    assert result.output_json["count"] == 0
    assert "playwright package not installed" in result.output_json["error"]
