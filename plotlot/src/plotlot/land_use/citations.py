"""Citation helpers for land-use evidence items."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import HttpUrl

from plotlot.land_use.models import EvidenceCitation, SourceType


def _to_http_url(url: str | None) -> HttpUrl | None:
    return HttpUrl(url) if url else None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ordinance_citation(
    *,
    title: str,
    url: str | None,
    jurisdiction: str | None,
    path: list[str] | None = None,
    publisher: str | None = "Municode/CivicPlus",
    raw_text_for_hash: str | None = None,
) -> EvidenceCitation:
    raw_hash = _sha256(raw_text_for_hash) if raw_text_for_hash else None
    return EvidenceCitation(
        source_type=SourceType.ORDINANCE,
        title=title,
        url=_to_http_url(url),
        jurisdiction=jurisdiction,
        path=list(path or []),
        retrieved_at=datetime.now(timezone.utc),
        publisher=publisher,
        raw_source_hash=raw_hash,
    )


def arcgis_layer_citation(
    *,
    title: str,
    service_url: str,
    jurisdiction: str | None,
    raw_text_for_hash: str | None = None,
    publisher: str | None = None,
) -> EvidenceCitation:
    raw_hash = _sha256(raw_text_for_hash) if raw_text_for_hash else None
    return EvidenceCitation(
        source_type=SourceType.ARCGIS_LAYER,
        title=title,
        url=_to_http_url(service_url),
        jurisdiction=jurisdiction,
        retrieved_at=datetime.now(timezone.utc),
        publisher=publisher,
        raw_source_hash=raw_hash,
    )


def county_record_citation(
    *,
    title: str,
    url: str | None,
    jurisdiction: str | None,
    publisher: str | None = None,
    raw_text_for_hash: str | None = None,
) -> EvidenceCitation:
    raw_hash = _sha256(raw_text_for_hash) if raw_text_for_hash else None
    return EvidenceCitation(
        source_type=SourceType.COUNTY_RECORD,
        title=title,
        url=_to_http_url(url),
        jurisdiction=jurisdiction,
        retrieved_at=datetime.now(timezone.utc),
        publisher=publisher,
        raw_source_hash=raw_hash,
    )


def geocode_citation(
    *,
    title: str,
    publisher: str | None,
    raw_text_for_hash: str | None = None,
) -> EvidenceCitation:
    raw_hash = _sha256(raw_text_for_hash) if raw_text_for_hash else None
    return EvidenceCitation(
        source_type=SourceType.WEB_PAGE,
        title=title,
        url=None,
        jurisdiction=None,
        retrieved_at=datetime.now(timezone.utc),
        publisher=publisher,
        raw_source_hash=raw_hash,
    )
