"""Adapter registry — resolves the correct SourceAdapter for any municipality.

Resolution order:
  1. Check _PDF_REGISTRY for known PDF-only municipalities (not on Municode)
  2. Try live Municode API discovery
  3. Try codifier platform discovery (Code Publishing / municipal.codes /
     eCode360 / American Legal) → generic WebCodifierAdapter
  4. Raise NoAdapterError if nothing found

Adding a new municipality:
  - If it's on Municode or a known codifier platform → nothing to do
    (auto-discovered)
  - If it's PDF-only → add one entry to _PDF_REGISTRY and one factory function
  - If it's custom HTML → build an HTMLAdapter manually (no registry entry needed
    since HTMLAdapter accepts an arbitrary URL list at construction time)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from plotlot.core.errors import NoAdapterError
from plotlot.core.types import MunicodeConfig
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.municode import MunicodeAdapter
from plotlot.ingestion.adapters.pdf import create_san_diego_adapter

logger = logging.getLogger(__name__)

# ── PDF-only municipality registry ───────────────────────────────────────────
#
# Key:   "{municipality_lowercase}_{state_lowercase}"  (space→underscore safe)
# Value: async factory () -> SourceAdapter
#
# New PDF-only municipality = one new entry here + one factory function.
# No new file required.

_PDF_REGISTRY: dict[str, Callable[[], Awaitable[SourceAdapter]]] = {
    "san diego_ca": create_san_diego_adapter,
}


# ── Public API ────────────────────────────────────────────────────────────────


async def resolve_adapter(
    municipality: str,
    state: str,
    county: str | None = None,
) -> SourceAdapter:
    """Resolve the correct SourceAdapter for a municipality.

    Args:
        municipality: City or unincorporated area name (e.g. "San Diego").
        state:        Two-letter state code (e.g. "CA").
        county:       Optional county name hint for Municode discovery.

    Returns:
        A ready-to-use SourceAdapter.

    Raises:
        NoAdapterError: When no source is found for the municipality.
    """
    key = _registry_key(municipality, state)

    # 1. Known PDF-only municipalities
    factory = _PDF_REGISTRY.get(key)
    if factory is not None:
        logger.info("registry_hit adapter=pdf municipality=%s state=%s", municipality, state)
        return await factory()

    # 2. Live Municode discovery
    config = await _try_municode(municipality, state, county)
    if config is not None:
        logger.info("registry_hit adapter=municode municipality=%s state=%s", municipality, state)
        return MunicodeAdapter(config)

    # 3. Codifier platform discovery (Code Publishing, municipal.codes,
    #    eCode360, American Legal) — deterministic URL probing, no keys needed.
    adapter = await _try_codifier(municipality, state, county)
    if adapter is not None:
        return adapter

    raise NoAdapterError(municipality, state)


def pdf_registered_municipalities() -> frozenset[str]:
    """Return the lowercased municipality names served by a PDF-only adapter.

    Derived from :data:`_PDF_REGISTRY` so callers (e.g. live ordinance search)
    can recognize non-Municode cities without hardcoding names. Registering one
    PDF city automatically extends this set.
    """
    return frozenset(key.rsplit("_", 1)[0] for key in _PDF_REGISTRY)


def register_pdf_municipality(
    municipality: str,
    state: str,
    factory: Callable[[], Awaitable[SourceAdapter]],
) -> None:
    """Register a PDF-only municipality at runtime (for testing or dynamic config).

    Args:
        municipality: City name.
        state:        Two-letter state code.
        factory:      Async callable that returns a configured SourceAdapter.
    """
    key = _registry_key(municipality, state)
    _PDF_REGISTRY[key] = factory
    logger.debug("registered pdf municipality key=%s", key)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _registry_key(municipality: str, state: str) -> str:
    """Normalise to lowercase registry key.  'San Diego', 'CA' → 'san diego_ca'."""
    return f"{municipality.strip().lower()}_{state.strip().lower()}"


async def _try_municode(
    municipality: str,
    state: str,
    county: str | None,
) -> MunicodeConfig | None:
    """Attempt live Municode API discovery.  Returns None on any failure."""
    try:
        from plotlot.ingestion.discovery import discover_municode_authority_for_name

        return await discover_municode_authority_for_name(municipality, state, county=county)
    except Exception as exc:
        logger.warning(
            "municode_discovery_failed municipality=%s state=%s error=%s",
            municipality,
            state,
            exc,
        )
        return None


async def _try_codifier(
    municipality: str,
    state: str,
    county: str | None,
) -> SourceAdapter | None:
    """Attempt codifier platform discovery.  Returns None on any failure."""
    try:
        from plotlot.ingestion.adapters.codifier import WebCodifierAdapter, discover_codifier

        hit = await discover_codifier(municipality, state)
        if hit is None:
            return None
        logger.info(
            "registry_hit adapter=codifier platform=%s municipality=%s state=%s",
            hit.platform,
            municipality,
            state,
        )
        return WebCodifierAdapter(
            municipality=municipality,
            county=county or "",
            state=state,
            hit=hit,
        )
    except Exception as exc:
        logger.warning(
            "codifier_discovery_failed municipality=%s state=%s error=%s",
            municipality,
            state,
            exc,
        )
        return None
