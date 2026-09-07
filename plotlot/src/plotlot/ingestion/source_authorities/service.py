"""Source authority service — provider priority + registry (Phase 2, master spec §5)."""

from __future__ import annotations

from plotlot.ingestion.source_authorities.models import Provider
from plotlot.ingestion.source_authorities.south_florida import seed_south_florida_authorities

# Master spec §5 provider priority (lower = higher priority).
_PROVIDER_PRIORITY: dict[Provider, int] = {
    Provider.OFFICIAL_HTML: 1,  # official API / machine-readable / HTML
    Provider.OFFICIAL_PDF: 2,
    Provider.MUNICODE: 3,
    Provider.ECODE360: 4,
    Provider.AMLEGAL: 5,
    Provider.CODEPUBLISHING: 6,
    Provider.MUNICIPAL_CODES: 7,
    Provider.ENCODEPLUS: 8,
    Provider.ARCGIS: 9,  # gis_zoning, not ordinance text
    Provider.MANUAL: 10,
}


def resolve_provider_priority(provider: Provider) -> int:
    """Return the priority rank (lower = preferred). Master spec §5."""
    return _PROVIDER_PRIORITY[provider]


def best_provider(providers: list[Provider]) -> Provider:
    """Pick the highest-priority provider from a set."""
    return min(providers, key=resolve_provider_priority)


__all__ = [
    "best_provider",
    "resolve_provider_priority",
    "seed_south_florida_authorities",
]
