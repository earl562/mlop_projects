"""Provider registry — maps county names to PropertyProvider instances.

Registration happens at import time via :func:`register_provider`.
The :func:`get_provider` lookup is case-insensitive and handles common
aliases (e.g., "miami dade" and "miami-dade" both resolve to MDC).
"""

from __future__ import annotations

import logging

from plotlot.property.base import PropertyProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, PropertyProvider] = {}
_initialized = False


def _ensure_registered() -> None:
    """Lazily import ``plotlot.property`` to trigger provider registration.

    This avoids circular imports: the provider modules import helpers from
    ``plotlot.retrieval.property``, which in turn calls ``get_provider``
    here at *runtime* (not import time).  The first ``get_provider`` call
    triggers a one-time import of the package ``__init__`` that registers
    all built-in providers.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return
    _initialized = True
    import plotlot.property  # noqa: F401 — side-effect: registers providers


def get_provider(county: str) -> PropertyProvider | None:
    """Return the registered provider for *county*, or ``None``.

    Lookup is case-insensitive and strips whitespace.
    """
    _ensure_registered()
    key = county.lower().strip()
    return _PROVIDERS.get(key)


def register_provider(county: str, provider: PropertyProvider) -> None:
    """Register *provider* under one or more *county* key(s).

    Args:
        county: Canonical county key (lowercased, stripped).
        provider: Concrete :class:`PropertyProvider` instance.
    """
    key = county.lower().strip()
    _PROVIDERS[key] = provider
    logger.debug("Registered PropertyProvider for '%s': %s", key, type(provider).__name__)


def registered_counties() -> frozenset[str]:
    """Return the set of county keys that have a registered provider."""
    return frozenset(_PROVIDERS)
