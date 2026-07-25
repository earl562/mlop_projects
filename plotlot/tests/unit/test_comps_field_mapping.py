"""Contract test: field-mapper resolves the registered South FL field names (slice 1.2).

The registry test (test_comps_sources_south_fl.py) only checks the sources are
registered. This test checks the next layer down: that comps.py's _find_field
actually resolves a price + date field for each registered county. Without this,
find_comparables silently returns 0 comps (price_field=None) even though the
layer is registered.

This caught the real bug: _find_field did exact case-insensitive matching, so
Broward's DB-qualified "SQLGIS02.dbo.BCPA_SALES.SALE_AMOUNT" and Miami-Dade's
"PRICE_1" never matched the candidate sets {SALE_AMT, PRICE, ...} / {SALE_DATE, ...}.
"""

from __future__ import annotations

from plotlot.pipeline.comps import _DATE_FIELDS, _PRICE_FIELDS, _find_field
from plotlot.pipeline.comps_sources import get_sales_source


def test_miami_dade_price_and_date_fields_resolve():
    src = get_sales_source("FL", "Miami-Dade")
    assert src is not None
    price = _find_field(list(src.fields), _PRICE_FIELDS)
    date = _find_field(list(src.fields), _DATE_FIELDS)
    assert price is not None, f"price field not resolved for Miami-Dade from {src.fields}"
    assert date is not None, f"date field not resolved for Miami-Dade from {src.fields}"


def test_broward_price_and_date_fields_resolve():
    src = get_sales_source("FL", "Broward")
    assert src is not None
    price = _find_field(list(src.fields), _PRICE_FIELDS)
    date = _find_field(list(src.fields), _DATE_FIELDS)
    assert price is not None, f"price field not resolved for Broward from {src.fields}"
    assert date is not None, f"date field not resolved for Broward from {src.fields}"


def test_palm_beach_price_and_date_fields_resolve():
    src = get_sales_source("FL", "Palm Beach")
    assert src is not None
    price = _find_field(list(src.fields), _PRICE_FIELDS)
    date = _find_field(list(src.fields), _DATE_FIELDS)
    assert price is not None, f"price field not resolved for Palm Beach from {src.fields}"
    assert date is not None, f"date field not resolved for Palm Beach from {src.fields}"
