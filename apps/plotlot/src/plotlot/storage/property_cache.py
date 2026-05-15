"""Local JSON cache for ArcGIS dataset discovery and field mappings.

This is an open, file-backed replacement for the previous cloud cache. It keeps
the same async function names used by ``UniversalProvider`` while storing data
under ``settings.property_cache_path``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plotlot.config import settings
from plotlot.property.models import CountyCache, FieldMapping

logger = logging.getLogger(__name__)


def _cache_path() -> Path:
    path = Path(settings.property_cache_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _empty_cache() -> dict[str, dict[str, Any]]:
    return {"county_datasets": {}, "field_mappings": {}}


def _read_cache() -> dict[str, dict[str, Any]]:
    path = _cache_path()
    if not path.exists():
        return _empty_cache()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Local property cache unreadable; ignoring %s", path, exc_info=True)
        return _empty_cache()
    if not isinstance(payload, dict):
        return _empty_cache()
    return {
        "county_datasets": payload.get("county_datasets") or {},
        "field_mappings": payload.get("field_mappings") or {},
    }


def _write_cache(payload: dict[str, dict[str, Any]]) -> None:
    path = _cache_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


async def get_county_cache(county_key: str) -> CountyCache | None:
    """Retrieve cached county data from the local JSON cache."""

    raw = _read_cache()["county_datasets"].get(county_key)
    if not raw:
        return None
    try:
        cache = CountyCache.model_validate(raw)
    except Exception:
        logger.warning("Invalid local county cache entry for %s", county_key, exc_info=True)
        return None

    age_hours = (datetime.now(timezone.utc) - cache.last_verified).total_seconds() / 3600
    if age_hours > cache.ttl_hours:
        logger.info("Local county cache expired for %s (%.1f hours old)", county_key, age_hours)
        return None
    return cache


async def save_county_cache(cache: CountyCache) -> None:
    """Save county dataset discovery to the local JSON cache."""

    payload = _read_cache()
    payload["county_datasets"][cache.county_key] = cache.model_dump(mode="json")
    _write_cache(payload)


async def get_field_mapping(county_key: str) -> FieldMapping | None:
    """Retrieve a cached field mapping from the local JSON cache."""

    raw = _read_cache()["field_mappings"].get(county_key)
    if not raw:
        return None
    try:
        return FieldMapping.model_validate(raw)
    except Exception:
        logger.warning("Invalid local field mapping cache entry for %s", county_key, exc_info=True)
        return None


async def save_field_mapping(mapping: FieldMapping) -> None:
    """Save a field mapping to the local JSON cache."""

    payload = _read_cache()
    payload["field_mappings"][mapping.county_key] = mapping.model_dump(mode="json")
    _write_cache(payload)
