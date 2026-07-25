"""Tests for chat generate_document context assembly (regressions for bugs 2 & 5).

Bug 2: state_code defaulted to "FL" regardless of the property's location.
Bug 5: the report-extraction block was dead code (session store get() returns
None), so chat-generated documents pulled nothing from the analysis — and it
referenced non-existent attributes (comp_count / confidence_score).
"""

import pytest

from plotlot.api.chat import _build_deal_context_data, _sessions


@pytest.fixture
def sid():
    s = "test-doc-ctx-session"
    _sessions.set_property_context(
        s,
        {
            "address": "1233 Hueneme St, San Diego, CA 92110",
            "municipality": "San Diego",
            "county": "San Diego",
            "zoning_code": "RM-3-7",
            "zoning_description": "Multifamily residential",
            "lot_size_sqft": 6470,
        },
    )
    _sessions.set_geocode(s, {"state": "CA", "lat": 32.76, "lng": -117.18})
    yield s
    _sessions._property_context.pop(s, None)
    _sessions._geocode.pop(s, None)


class TestBuildDealContextData:
    def test_state_from_geocode_not_hardcoded_fl(self, sid):
        # Bug 2: state must come from the geocode, not a hardcoded "FL".
        ctx = _build_deal_context_data(sid, {})
        assert ctx["state_code"] == "CA"

    def test_property_fields_extracted(self, sid):
        # Bug 5: the available property context must flow into the document.
        ctx = _build_deal_context_data(sid, {})
        assert ctx["property_address"].startswith("1233 Hueneme")
        assert ctx["municipality"] == "San Diego"
        assert ctx["county"] == "San Diego"
        assert ctx["zoning_district"] == "RM-3-7"
        assert ctx["zoning_description"] == "Multifamily residential"
        assert ctx["lot_size_sqft"] == 6470

    def test_explicit_args_override_session(self, sid):
        ctx = _build_deal_context_data(
            sid,
            {
                "state_code": "TX",
                "buyer_name": "Acme LLC",
                "purchase_price": 500000,
                "financing_type": "seller_carryback",
            },
        )
        assert ctx["state_code"] == "TX"  # arg overrides geocode CA
        assert ctx["buyer_name"] == "Acme LLC"
        assert ctx["purchase_price"] == 500000
        assert ctx["financing_type"] == "seller_carryback"  # bug 8: now settable

    def test_empty_session_is_safe(self):
        ctx = _build_deal_context_data("no-such-session", {})
        assert isinstance(ctx, dict)
        # No geocode → no state injected (AssemblyConfig applies its own fallback).
        assert "state_code" not in ctx

    def test_no_bogus_comp_attributes(self, sid):
        # Regression: the old dead block referenced comp_count / confidence_score,
        # which don't exist on CompAnalysis. The builder must never emit them.
        ctx = _build_deal_context_data(sid, {})
        assert "comp_count" not in ctx
        assert "comp_confidence" not in ctx

    def test_deterministic(self, sid):
        runs = [_build_deal_context_data(sid, {}) for _ in range(10)]
        assert all(r == runs[0] for r in runs)
