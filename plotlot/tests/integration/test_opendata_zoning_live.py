"""Live integration test: OpenData/ArcGIS zoning-label queries across 3 South FL
counties (Slice 8.0 — the OpenData half of the data foundation).

Architecture doc §4.4 (OpenData Service) + §15. The OpenData source returns the
zoning district LABEL per parcel (origin=local_authority, source_url=FeatureServer
query) — the fast path the agent joins with Municode dimensional standards.

Three county zoning servers, already live (no re-scraping needed):
  * Miami-Dade: gisweb.miamidade.gov (municipal + unincorporated)
  * Broward:    gisweb-adapters.bcpa.net
  * Palm Beach: maps.co.palm-beach.fl.us
= ~60+ South FL municipalities.

MARKED live — requires network access to county ArcGIS servers.

    PLOTLOT_LIVE_TESTS=1 uv run pytest tests/integration/test_opendata_zoning_live.py -v
"""

from __future__ import annotations

import os

import pytest

from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 (hits county ArcGIS servers)"
)

# Real addresses across the 3 South FL counties — one per city, proving the
# OpenData path serves the whole region, not just one municipality.
SOUTH_FL_PROBES = [
    # Broward County (gisweb-adapters.bcpa.net)
    ("101 SE 1st Ave, Fort Lauderdale, FL 33301", "Broward"),
    ("1234 NW 15th St, Fort Lauderdale, FL 33311", "Broward"),
    ("1900 Van Buren St, Hollywood, FL 33020", "Broward"),
    ("500 NE 48th St, Oakland Park, FL 33334", "Broward"),
    # Miami-Dade County (gisweb.miamidade.gov)
    ("1400 S Dixie Hwy, Coral Gables, FL 33146", "Miami-Dade"),
    ("1600 NW 7th Ave, Miami, FL 33136", "Miami-Dade"),
    ("100 Ocean Dr, Miami Beach, FL 33139", "Miami-Dade"),
    # Palm Beach County (maps.co.palm-beach.fl.us)
    ("301 N Olive Ave, West Palm Beach, FL 33401", "Palm Beach"),
    ("201 W Palmetto Park Rd, Boca Raton, FL 33432", "Palm Beach"),
    ("500 S Olive Ave, West Palm Beach, FL 33401", "Palm Beach"),
]


@pytest.mark.asyncio
async def test_opendata_returns_zoning_labels_across_3_counties():
    """The OpenData path returns a real zoning district label for parcels
    across Broward, Miami-Dade, and Palm Beach counties — ~60+ municipalities.
    This is the fast-path verified-fact source (origin=local_authority) the
    agent joins with Municode dimensional standards."""
    hits = 0
    for address, county in SOUTH_FL_PROBES:
        geo = await geocode_address(address)
        assert geo is not None, f"geocode failed for {address}"
        pr = await lookup_property(address, county, lat=geo["lat"], lng=geo["lng"])
        assert pr is not None, f"{county}/{address}: no property record"
        assert pr.zoning_code, (
            f"{county}/{address}: no zoning_code — the spatial zoning query needs "
            f"geocoded coords when the property feature lacks geometry"
        )
        # The label must be a real zoning code, not empty/whitespace.
        assert pr.zoning_code.strip(), f"{county}/{address}: empty zoning_code"
        print(f"  + {county:11}: {pr.zoning_code:16} ({address})")
        hits += 1
    assert hits >= 8, f"expected >=8/10 OpenData hits across 3 counties, got {hits}"


@pytest.mark.asyncio
async def test_broward_zoning_uses_geocoded_fallback_when_feature_lacks_geometry():
    """Broward's MapServer returns property features WITHOUT geometry, so the
    spatial zoning query must fall back to the geocoded lat/lng. This pins
    that fallback (the fix for the Broward no-zoning bug)."""
    address = "101 SE 1st Ave, Fort Lauderdale, FL 33301"
    geo = await geocode_address(address)
    pr = await lookup_property(address, "Broward", lat=geo["lat"], lng=geo["lng"])
    assert pr is not None and pr.zoning_code
    assert pr.zoning_code == "RAC-CC"  # verified Fort Lauderdale downtown label
