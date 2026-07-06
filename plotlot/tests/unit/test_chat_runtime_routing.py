"""Tests for chat's harness-runtime routing layer.

Chat executes every tool through HarnessRuntime.call_tool; these tests guard
the two things that make that safe:

1. Coverage — a chat tool missing from _RUNTIME_ROUTED_TOOLS silently falls
   back to the ungoverned bespoke path (no policy/evidence/audit). That exact
   gap is how analyze_property ran ungoverned for months.
2. Session mirroring — harness handlers are session-free, so the routing layer
   must persist the grounded analyze payload into the SessionStore or every
   follow-up turn loses grounding (and the cold ~minute pipeline would re-run
   on repeat calls without the cache short-circuit).
"""

import uuid

from plotlot.api.chat import (
    CHAT_TOOLS,
    _RUNTIME_ROUTED_TOOLS,
    _cached_grounded_analysis,
    _mirror_grounded_analysis_to_session,
    _sessions,
)
from plotlot.harness.default_runtime import build_default_runtime
from plotlot.harness.tool_registry import tool_exists


def _sid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Coverage guards
# ---------------------------------------------------------------------------


def test_every_chat_tool_is_runtime_routed():
    chat_tool_names = {t["function"]["name"] for t in CHAT_TOOLS}
    unrouted = chat_tool_names - _RUNTIME_ROUTED_TOOLS
    assert not unrouted, (
        f"chat tools NOT routed through the harness runtime (ungoverned): {sorted(unrouted)}"
    )


def test_every_routed_tool_has_contract_and_handler():
    runtime = build_default_runtime()
    for name in sorted(_RUNTIME_ROUTED_TOOLS):
        assert tool_exists(name), f"routed tool {name} has no contract"
        assert runtime.has_handler(name), f"routed tool {name} has no handler"


# ---------------------------------------------------------------------------
# Session mirroring (grounding persistence)
# ---------------------------------------------------------------------------


def test_mirror_persists_analysis_and_property_context():
    sid = _sid()
    payload = {
        "status": "success",
        "address": "1233 Hueneme St, San Diego, CA 92110",
        "municipality": "San Diego",
        "county": "San Diego",
        "state": "CA",
        "zoning_code": "RM-3-7",
        "zoning_description": "Residential multifamily",
        "lot_size_sqft": 7710,
        "owner": "1233 HUENEME LLC",
        "by_right": {"max_units": 7},
    }

    _mirror_grounded_analysis_to_session(sid, payload)

    assert _sessions.get_analysis(sid) == payload
    ctx = _sessions.get_property_context(sid)
    assert ctx is not None
    assert ctx["owner"] == "1233 HUENEME LLC"
    assert ctx["zoning_code"] == "RM-3-7"
    assert ctx["lot_size_sqft"] == 7710
    assert ctx["state"] == "CA"


def test_mirror_skips_non_success_payloads():
    sid = _sid()
    _mirror_grounded_analysis_to_session(sid, {"status": "error", "message": "boom"})
    _mirror_grounded_analysis_to_session(sid, {"status": "not_found", "message": "nope"})
    _mirror_grounded_analysis_to_session(sid, None)
    assert _sessions.get_analysis(sid) is None
    assert _sessions.get_property_context(sid) is None


def test_mirror_without_jurisdiction_sets_analysis_only():
    sid = _sid()
    payload = {"status": "success", "address": "somewhere", "by_right": {"max_units": 2}}
    _mirror_grounded_analysis_to_session(sid, payload)
    assert _sessions.get_analysis(sid) == payload
    assert _sessions.get_property_context(sid) is None


# ---------------------------------------------------------------------------
# Cache short-circuit (latency guard)
# ---------------------------------------------------------------------------


def test_cached_analysis_returned_for_covered_address():
    sid = _sid()
    payload = {"status": "success", "address": "1233 Hueneme St, San Diego, CA 92110"}
    _sessions.set_analysis(sid, payload)
    assert _cached_grounded_analysis(sid, "1233 Hueneme St, San Diego, CA 92110") == payload


def test_cached_analysis_misses_for_other_address_or_session():
    sid = _sid()
    _sessions.set_analysis(sid, {"status": "success", "address": "1233 Hueneme St"})
    assert _cached_grounded_analysis(sid, "456 Oak Ave") is None
    assert _cached_grounded_analysis(_sid(), "1233 Hueneme St") is None
    assert _cached_grounded_analysis("", "1233 Hueneme St") is None
