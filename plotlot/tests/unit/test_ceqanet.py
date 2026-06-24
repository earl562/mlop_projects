"""Tests for the CEQAnet client + two-tier parcel matcher (pipeline/ceqanet.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from plotlot.core.types import CEQADocument
from plotlot.pipeline.ceqanet import (
    _address_tokens,
    _dms_to_decimal,
    _haversine_m,
    _normalize_apn,
    _parse_ceqa_csv,
    fetch_ceqa_documents,
    match_ceqa_documents,
)

# A compact CSV using the real CEQAnet column names (parser reads by header).
# Per RFC 4180, the literal " in the DMS coordinate is escaped by doubling it,
# exactly as CEQAnet's real export does.
_CSV = (
    "SCH Number,Document Type,Received,Document Description,Lead Agency Name,"
    "Document Portal URL,Document Title,Location Coordinates,Location Parcel Number,"
    "Location Cross Streets,Location Zip Code,Cities,Counties,Contact Full Name\n"
    "2024010001,EIR,1/2/2024,A big project,City of San Diego,"
    "https://ceqanet.lci.ca.gov/2024010001,Hueneme Mixed Use,"
    '"32°42\'8""N 117°10\'46.1""W",760-057-00-02,1st & J,92118,San Diego,San Diego,Jane Doe\n'
    "2024010002,NOE,2/2/2024,Statewide rulemaking,State Agency,"
    "https://ceqanet.lci.ca.gov/2024010002,Statewide Rule,,Unparcelled Public Trust Lands,,,"
    '"Adelanto, Agoura",Alameda,John Roe\n'
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_dms_to_decimal():
    latlng = _dms_to_decimal("32°42'8\"N 117°10'46.1\"W")
    assert latlng is not None
    lat, lng = latlng
    assert abs(lat - 32.70222) < 0.001
    assert abs(lng - (-117.17947)) < 0.001


def test_dms_with_seconds_not_misread_as_decimal():
    # Regression (live bug): a DMS string with DECIMAL seconds must parse to the
    # real coordinate, never fall through to the decimal path and return the
    # seconds (47.8, 24.1) as if they were lat/lng.
    latlng = _dms_to_decimal("32°37'47.8\"N 117°8'24.1\"W")
    assert latlng is not None
    lat, lng = latlng
    assert 32.5 < lat < 32.7  # ~32.6299, NOT 47.8
    assert -117.2 < lng < -117.1  # ~-117.140, NOT 24.1


def test_dms_decimal_fallback_and_empty():
    assert _dms_to_decimal("") is None
    dec = _dms_to_decimal("32.7022, -117.1795")
    assert dec is not None and abs(dec[0] - 32.7022) < 1e-6
    # A compass-bearing string that cannot be parsed returns None, not garbage.
    assert _dms_to_decimal("North of 47.8 and 24.1 W") is None


def test_haversine_known_distance():
    # 1 degree of longitude at the equator ≈ 111.19 km.
    assert abs(_haversine_m(0.0, 0.0, 0.0, 1.0) - 111_195) < 500


def test_normalize_apn():
    assert _normalize_apn("760-057-00-02") == "7600570002"
    assert _normalize_apn("Unparcelled Public Trust Lands") == ""
    assert _normalize_apn("") == ""


def test_address_tokens():
    assert _address_tokens("1233 Hueneme St, San Diego, CA 92110") == ("1233", "hueneme")
    assert _address_tokens("") == ("", "")


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def test_parse_ceqa_csv():
    docs = _parse_ceqa_csv(_CSV)
    assert len(docs) == 2
    d0 = docs[0]
    assert d0.sch_number == "2024010001"
    assert d0.doc_type == "EIR"
    assert d0.parcel_number == "760-057-00-02"
    assert d0.lat is not None and abs(d0.lat - 32.70222) < 0.001
    assert d0.source_url.endswith("2024010001")
    # Statewide row has no coordinates.
    assert docs[1].lat is None


# ---------------------------------------------------------------------------
# Matching — Tier 1 strong
# ---------------------------------------------------------------------------


def _doc(**kw):
    base = dict(doc_type="MND", sch_number="S1")
    base.update(kw)
    return CEQADocument(**base)


def test_match_apn_exact_is_strong():
    docs = [_doc(parcel_number="760-057-00-02", sch_number="A")]
    strong, cand = match_ceqa_documents(docs, parcel_apn="7600570002")
    assert len(strong) == 1 and not cand
    assert strong[0].match_tier == "strong" and strong[0].on_parcel is True
    assert "APN" in strong[0].match_basis


def test_match_coordinates_within_radius_is_strong():
    docs = [_doc(lat=32.70225, lng=-117.17950, sch_number="B")]
    strong, cand = match_ceqa_documents(docs, parcel_lat=32.70222, parcel_lng=-117.17947)
    assert len(strong) == 1 and strong[0].match_tier == "strong"
    assert strong[0].distance_m is not None and strong[0].distance_m < 150


def test_match_exact_address_in_record_is_strong():
    docs = [_doc(title="1233 Hueneme Street Redevelopment", sch_number="C")]
    strong, cand = match_ceqa_documents(docs, parcel_address="1233 Hueneme St, San Diego")
    assert len(strong) == 1 and strong[0].match_tier == "strong"
    assert "address" in strong[0].match_basis


# ---------------------------------------------------------------------------
# Matching — Tier 2 candidate / drop
# ---------------------------------------------------------------------------


def test_match_nearby_coordinates_is_candidate():
    docs = [_doc(lat=32.710, lng=-117.180, sch_number="D")]  # ~900m away
    strong, cand = match_ceqa_documents(docs, parcel_lat=32.70222, parcel_lng=-117.17947)
    assert not strong and len(cand) == 1
    assert cand[0].match_tier == "candidate" and cand[0].on_parcel is False


def test_same_city_no_signal_is_dropped():
    # No APN, no coords, no address/owner/zip overlap → must NOT surface at all.
    docs = [_doc(title="Some Unrelated Park Project", sch_number="E")]
    strong, cand = match_ceqa_documents(
        docs, parcel_address="1233 Hueneme St", parcel_apn="7600570002"
    )
    assert not strong and not cand


def test_strong_project_never_also_a_candidate_and_dedup_by_sch():
    docs = [
        _doc(parcel_number="760-057-00-02", sch_number="X", doc_type="NOP"),
        _doc(parcel_number="760-057-00-02", sch_number="X", doc_type="EIR"),
        _doc(lat=32.710, lng=-117.180, sch_number="X"),  # same project, weaker
    ]
    strong, cand = match_ceqa_documents(
        docs, parcel_apn="7600570002", parcel_lat=32.70222, parcel_lng=-117.17947
    )
    assert len(strong) == 1  # deduped to one project
    assert all(c.sch_number != "X" for c in cand)  # never appears as candidate
    assert strong[0].status == "in_progress" and strong[0].doc_type == "EIR"


# ---------------------------------------------------------------------------
# fetch_ceqa_documents — network gated, graceful
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, text="", ctype="text/csv"):
        self.text = text
        self.content = text.encode("utf-8")  # fetch decodes bytes via _decode_csv
        self.headers = {"content-type": ctype}

    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        return self._resp


@pytest.mark.asyncio
async def test_fetch_parses_csv():
    with patch(
        "plotlot.pipeline.ceqanet.httpx.AsyncClient", return_value=_FakeClient(_FakeResp(_CSV))
    ):
        docs = await fetch_ceqa_documents("San Diego", "San Diego")
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_fetch_non_csv_returns_empty():
    # >10k results → CEQAnet returns HTML, not CSV → degrade to empty.
    html = _FakeResp("<html>too many results</html>", ctype="text/html")
    with patch("plotlot.pipeline.ceqanet.httpx.AsyncClient", return_value=_FakeClient(html)):
        docs = await fetch_ceqa_documents("San Diego", "San Diego")
    assert docs == []


@pytest.mark.asyncio
async def test_fetch_missing_inputs_returns_empty():
    assert await fetch_ceqa_documents("", "") == []
