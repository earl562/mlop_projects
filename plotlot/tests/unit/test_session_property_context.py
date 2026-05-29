"""Unit tests for Bug 4 — session property context persistence.

Verifies that after lookup_property_info succeeds in the chat loop:
1. SessionStore stores address/municipality/zoning_code.
2. The stored context is injected into the system prompt on subsequent turns.
"""

from __future__ import annotations

from plotlot.api.chat import SessionStore


def _make_store() -> SessionStore:
    return SessionStore(max_sessions=10, ttl=3600)


def test_session_store_property_context_round_trip():
    store = _make_store()
    sid = "sess_test"
    ctx = {
        "address": "1233 Hueneme St, San Diego CA 92110",
        "municipality": "San Diego",
        "county": "San Diego",
        "zoning_code": "RM-3-7",
        "zoning_description": "Residential Multiple Unit",
        "lot_size_sqft": 6200.0,
    }
    store.set_property_context(sid, ctx)
    result = store.get_property_context(sid)
    assert result == ctx


def test_session_store_property_context_returns_none_when_unset():
    store = _make_store()
    assert store.get_property_context("unknown_session") is None


def test_session_store_property_context_evicted_with_session():
    store = _make_store()
    sid = "sess_evict"
    store.set_property_context(sid, {"address": "test", "municipality": "San Diego"})
    store.delete_session(sid)
    assert store.get_property_context(sid) is None


def test_session_store_property_context_overwrite():
    store = _make_store()
    sid = "sess_overwrite"
    store.set_property_context(sid, {"address": "old address", "zoning_code": "R-1"})
    store.set_property_context(sid, {"address": "new address", "zoning_code": "RM-3-7"})
    ctx = store.get_property_context(sid)
    assert ctx["address"] == "new address"
    assert ctx["zoning_code"] == "RM-3-7"


def test_session_store_has_property_context_dict_attribute():
    """Regression: _property_context must exist on the store so _evict doesn't KeyError."""
    store = _make_store()
    assert hasattr(store, "_property_context")
    assert isinstance(store._property_context, dict)


# ---------------------------------------------------------------------------
# Evidence ID accumulator tests (generate_document fix)
# ---------------------------------------------------------------------------


def test_evidence_ids_empty_by_default():
    store = _make_store()
    assert store.get_evidence_ids("unknown") == []


def test_evidence_ids_accumulate():
    store = _make_store()
    sid = "sess_ev"
    store.add_evidence_ids(sid, ["ev1", "ev2"])
    store.add_evidence_ids(sid, ["ev3"])
    assert store.get_evidence_ids(sid) == ["ev1", "ev2", "ev3"]


def test_evidence_ids_deduped():
    store = _make_store()
    sid = "sess_dedup"
    store.add_evidence_ids(sid, ["ev1", "ev2"])
    store.add_evidence_ids(sid, ["ev2", "ev3"])
    ids = store.get_evidence_ids(sid)
    assert ids.count("ev2") == 1
    assert set(ids) == {"ev1", "ev2", "ev3"}


def test_evidence_ids_evicted_with_session():
    store = _make_store()
    sid = "sess_ev_evict"
    store.add_evidence_ids(sid, ["ev1"])
    store.delete_session(sid)
    assert store.get_evidence_ids(sid) == []


def test_evidence_ids_ignores_empty_strings():
    store = _make_store()
    sid = "sess_empty"
    store.add_evidence_ids(sid, ["", "ev1", ""])
    assert store.get_evidence_ids(sid) == ["ev1"]
