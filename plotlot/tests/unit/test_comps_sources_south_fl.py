"""Contract test for curated South FL sales sources (slice 1.2).

Pins that the curated ArcGIS sales layers are registered for the three South FL
counties (Miami-Dade, Broward, Palm Beach), each with the verified sale-price +
sale-date field names. These replace RentCast (not free) and the unreliable
generic ArcGIS Hub keyword discovery.

Verified live 2026-06-26:
- Miami-Dade PaGISView layer 0: PRICE_1, DATEOFSALE_UTC
- Broward BCPA layer 18 (2025 Sales): SALE_AMOUNT, SALE_DATE
- Palm Beach Parcels layer 0: PRICE, SALE_DATE
"""

from __future__ import annotations

from plotlot.pipeline.comps_sources import get_sales_source


def test_miami_dade_sales_source_registered():
    src = get_sales_source("FL", "Miami-Dade")
    assert src is not None, "Miami-Dade curated sales source not registered"
    assert src.layer_url, "missing layer_url"
    assert "arcgis" in src.layer_url.lower(), f"expected ArcGIS URL, got {src.layer_url}"
    field_names = {f.upper() for f in src.fields}
    assert "PRICE_1" in field_names, f"PRICE_1 missing from {src.fields}"
    assert "DATEOFSALE_UTC" in field_names, f"DATEOFSALE_UTC missing from {src.fields}"
    assert src.source, "missing provenance/source citation"


def test_broward_sales_source_registered():
    src = get_sales_source("FL", "Broward")
    assert src is not None, "Broward curated sales source not registered"
    assert src.layer_url, "missing layer_url"
    assert "bcpa" in src.layer_url.lower(), f"expected BCPA URL, got {src.layer_url}"
    field_names = {f.upper() for f in src.fields}
    # Broward 2025 sales layer uses dotted DB-qualified names; the field mapper
    # matches on substring, so we accept either the bare or qualified name.
    has_sale_amount = any("SALE_AMOUNT" in f for f in field_names)
    has_sale_date = any("SALE_DATE" in f for f in field_names)
    assert has_sale_amount, f"SALE_AMOUNT missing from {src.fields}"
    assert has_sale_date, f"SALE_DATE missing from {src.fields}"
    assert src.source, "missing provenance/source citation"


def test_palm_beach_sales_source_registered():
    src = get_sales_source("FL", "Palm Beach")
    assert src is not None, "Palm Beach curated sales source not registered"
    assert src.layer_url, "missing layer_url"
    assert "arcgis" in src.layer_url.lower(), f"expected ArcGIS URL, got {src.layer_url}"
    field_names = {f.upper() for f in src.fields}
    assert "PRICE" in field_names, f"PRICE missing from {src.fields}"
    assert "SALE_DATE" in field_names, f"SALE_DATE missing from {src.fields}"
    assert src.source, "missing provenance/source citation"


def test_resolve_returns_curated_source_for_south_fl():
    """resolve_sales_dataset returns the curated layer (not None) for South FL,
    so find_comparables skips the noisy Hub keyword discovery."""
    import asyncio
    from plotlot.pipeline.comps_sources import resolve_sales_dataset

    for county in ("Miami-Dade", "Broward", "Palm Beach"):
        result = asyncio.run(resolve_sales_dataset("FL", county, 26.1, -80.1, 3.0))
        assert result is not None, f"resolve returned None for {county}"
        layer_url, fields = result
        assert layer_url, f"empty layer_url for {county}"
        assert fields, f"empty fields for {county}"
