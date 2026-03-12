"""Tests for the building render endpoint (AI architectural visualization)."""

import base64
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from plotlot.api.render import (
    BuildingRenderRequest,
    _cache,
    _cache_key,
    build_architectural_prompt,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_request(**overrides) -> BuildingRenderRequest:
    defaults = {
        "property_type": "single_family",
        "stories": 2,
        "total_width_ft": 45.0,
        "total_depth_ft": 80.0,
        "max_height_ft": 35.0,
        "lot_width_ft": 75.0,
        "lot_depth_ft": 120.0,
        "zoning_district": "RS-1",
        "unit_count": 1,
        "setback_front_ft": 25.0,
        "setback_side_ft": 15.0,
        "setback_rear_ft": 15.0,
        "municipality": "Miami Gardens",
    }
    defaults.update(overrides)
    return BuildingRenderRequest(**defaults)


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------


def test_build_prompt_single_family():
    req = _make_request(property_type="single_family")
    prompt = build_architectural_prompt(req)
    assert "single-family" in prompt.lower()
    assert "45" in prompt  # width
    assert "80" in prompt  # depth
    assert "stucco" in prompt.lower()
    assert "Miami Gardens" in prompt
    # Room program details
    assert "front porch" in prompt.lower()
    assert "garage" in prompt.lower()
    assert "master suite" in prompt.lower()
    assert "walk-in closet" in prompt.lower()
    assert "kitchen" in prompt.lower()
    # Setback context
    assert "25 ft front yard" in prompt
    assert "15 ft side yards" in prompt


def test_build_prompt_multifamily():
    req = _make_request(property_type="multifamily", stories=3, unit_count=8)
    prompt = build_architectural_prompt(req)
    assert "multifamily" in prompt.lower()
    assert "flat roof" in prompt.lower()
    assert "8 dwelling units" in prompt
    # Room program
    assert "corridor" in prompt.lower()
    assert "lobby" in prompt.lower()
    assert "balcon" in prompt.lower()
    assert "8 total dwelling units across 3 floors" in prompt


def test_build_prompt_commercial():
    req = _make_request(property_type="commercial", stories=1)
    prompt = build_architectural_prompt(req)
    assert "commercial" in prompt.lower()
    assert "storefront" in prompt.lower()
    # Room program
    assert "lobby" in prompt.lower()
    assert "restroom" in prompt.lower()
    assert "mechanical" in prompt.lower()


def test_build_prompt_duplex():
    req = _make_request(property_type="duplex", stories=2, unit_count=2)
    prompt = build_architectural_prompt(req)
    assert "duplex" in prompt.lower()
    # Room program
    assert "shared center wall" in prompt.lower()
    assert "front entrance" in prompt.lower()
    assert "kitchen" in prompt.lower()
    assert "bedroom" in prompt.lower()


def test_build_prompt_land():
    req = _make_request(property_type="land", stories=0, unit_count=0)
    prompt = build_architectural_prompt(req)
    assert "vacant" in prompt.lower()
    # Land-specific details
    assert "survey stakes" in prompt.lower()
    assert "buildable envelope" in prompt.lower()
    assert "setbacks" in prompt.lower()


def test_build_prompt_no_municipality():
    req = _make_request(municipality="")
    prompt = build_architectural_prompt(req)
    assert "in Miami Gardens" not in prompt


def test_build_prompt_front_view():
    req = _make_request()
    prompt = build_architectural_prompt(req, view="front")
    assert "front elevation" in prompt.lower()


def test_build_prompt_aerial_view():
    req = _make_request()
    prompt = build_architectural_prompt(req, view="aerial")
    assert "aerial" in prompt.lower()
    assert "45 degrees" in prompt


def test_build_prompt_side_view():
    req = _make_request()
    prompt = build_architectural_prompt(req, view="side")
    assert "side elevation" in prompt.lower()


# ---------------------------------------------------------------------------
# Cache key tests
# ---------------------------------------------------------------------------


def test_cache_key_deterministic():
    req = _make_request()
    key1 = _cache_key(req)
    key2 = _cache_key(req)
    assert key1 == key2


def test_cache_key_rounding():
    """47ft and 48ft round to the same value (round to nearest 10)."""
    req1 = _make_request(total_width_ft=47.0)
    req2 = _make_request(total_width_ft=48.0)
    assert _cache_key(req1) == _cache_key(req2)


def test_cache_key_different_types():
    req1 = _make_request(property_type="single_family")
    req2 = _make_request(property_type="multifamily")
    assert _cache_key(req1) != _cache_key(req2)


# ---------------------------------------------------------------------------
# Cache behavior tests
# ---------------------------------------------------------------------------


def test_cache_hit():
    """Cache stores multi-view entries."""
    _cache.clear()
    req = _make_request()
    key = _cache_key(req)

    fake_b64 = base64.b64encode(b"fake-png-data").decode()
    _cache[key] = [
        ("front", fake_b64, "front prompt"),
        ("aerial", fake_b64, "aerial prompt"),
        ("side", fake_b64, "side prompt"),
    ]

    assert key in _cache
    assert len(_cache[key]) == 3
    assert _cache[key][0][0] == "front"
    _cache.clear()


# ---------------------------------------------------------------------------
# Endpoint tests (mocked Gemini)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Test client with mocked settings."""
    from plotlot.api.main import app

    _cache.clear()
    return TestClient(app)


@patch("plotlot.api.render.settings")
def test_render_no_api_key(mock_settings, client):
    """Graceful 503 when GOOGLE_API_KEY is not set."""
    mock_settings.google_api_key = ""
    resp = client.post(
        "/api/v1/render/building",
        json=_make_request().model_dump(),
    )
    assert resp.status_code == 503
    assert "GOOGLE_API_KEY" in resp.json()["detail"]


@patch("plotlot.api.render.generate_building_image")
@patch("plotlot.api.render.settings")
def test_render_endpoint_returns_three_views(mock_settings, mock_gen, client):
    """POST to endpoint returns 3 views (front, aerial, side)."""
    mock_settings.google_api_key = "test-key"
    fake_b64 = base64.b64encode(b"fake-png").decode()
    mock_gen.return_value = fake_b64

    resp = client.post(
        "/api/v1/render/building",
        json=_make_request().model_dump(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is False
    assert data["generation_time_ms"] >= 0
    assert len(data["views"]) == 3
    view_names = [v["view"] for v in data["views"]]
    assert view_names == ["front", "aerial", "side"]
    for v in data["views"]:
        assert v["image_base64"] == fake_b64
        assert "prompt_used" in v
    # Called once per view
    assert mock_gen.call_count == 3
    _cache.clear()


@patch("plotlot.api.render.generate_building_image")
@patch("plotlot.api.render.settings")
def test_render_endpoint_cache_hit(mock_settings, mock_gen, client):
    """Second identical request returns cached=True without calling Gemini."""
    mock_settings.google_api_key = "test-key"
    fake_b64 = base64.b64encode(b"fake-png").decode()
    mock_gen.return_value = fake_b64

    req_body = _make_request().model_dump()

    # First call
    resp1 = client.post("/api/v1/render/building", json=req_body)
    assert resp1.status_code == 200
    assert resp1.json()["cached"] is False
    assert len(resp1.json()["views"]) == 3

    # Second call — should be cached
    resp2 = client.post("/api/v1/render/building", json=req_body)
    assert resp2.status_code == 200
    assert resp2.json()["cached"] is True
    assert len(resp2.json()["views"]) == 3

    # Gemini should only be called 3 times (first request only)
    assert mock_gen.call_count == 3
    _cache.clear()


@patch("plotlot.api.render.generate_building_image")
@patch("plotlot.api.render.settings")
def test_render_partial_failure(mock_settings, mock_gen, client):
    """If one view fails, the others still return."""
    mock_settings.google_api_key = "test-key"
    fake_b64 = base64.b64encode(b"fake-png").decode()

    call_count = 0

    async def _side_effect(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # fail the aerial view
            raise ValueError("simulated failure")
        return fake_b64

    mock_gen.side_effect = _side_effect

    resp = client.post(
        "/api/v1/render/building",
        json=_make_request().model_dump(),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should have 2 views (front + side), aerial failed
    assert len(data["views"]) == 2
    _cache.clear()
