"""Property provider package — abstract interface + per-county implementations.

Usage::

    from plotlot.property import lookup_property, PropertyProvider, PropertyRecord

    record = await lookup_property("171 NE 209th Ter, Miami, FL", "Miami-Dade", lat=25.9, lng=-80.2)

Adding a new county is three steps:
  1. Create ``plotlot/property/<county>.py`` with a :class:`PropertyProvider` subclass.
  2. Register it below (or call :func:`register_provider` at startup).
  3. Done — ``lookup_property`` routes to it automatically.
"""

from typing import cast

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.property.registry import get_provider, register_provider, registered_counties

# Register built-in providers ---------------------------------------------------

from plotlot.property.broward import BrowardProvider
from plotlot.property.california import CaliforniaProvider
from plotlot.property.clark_county_nv import ClarkCountyNVProvider
from plotlot.property.mecklenburg import MecklenburgProvider
from plotlot.property.miami_dade import MiamiDadeProvider
from plotlot.property.palm_beach import PalmBeachProvider

# FL providers
_broward = BrowardProvider()
_miami_dade = MiamiDadeProvider()
_palm_beach = PalmBeachProvider()

register_provider("miami-dade", _miami_dade)
register_provider("miami dade", _miami_dade)  # alias — Geocodio sometimes omits hyphen
register_provider("broward", _broward)
register_provider("palm beach", _palm_beach)

# NV providers
_clark_county_nv = ClarkCountyNVProvider()

register_provider("clark", _clark_county_nv)  # Geocodio returns "Clark" for Clark County NV

# NC providers
_mecklenburg = MecklenburgProvider()

register_provider("mecklenburg", _mecklenburg)

# CA providers — five counties with ingested ordinance data
_california = CaliforniaProvider()

# Sacramento County (Citrus Heights, Lincoln, Rocklin)
register_provider("sacramento", _california)

# Contra Costa County (El Cerrito, Lafayette, Moraga, Orinda, Richmond)
register_provider("contra costa", _california)

# Alameda County (Alameda, Hayward, Newark, Oakland)
register_provider("alameda", _california)

# Santa Clara County (Campbell, Los Altos, Los Gatos, Milpitas, Monte Sereno,
#                     Morgan Hill, Mountain View, San Jose, Saratoga)
register_provider("santa clara", _california)

# San Mateo County (Daly City, East Palo Alto, Hillsborough, Portola Valley, Woodside)
register_provider("san mateo", _california)

# San Diego County — uses CA statewide parcel layer (no county-specific config needed)
register_provider("san diego", _california)


# Convenience top-level lookup ---------------------------------------------------


async def lookup_property(
    address: str,
    county: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    state: str = "",
) -> PropertyRecord | None:
    """Look up property data via the registered provider for *county*.

    This is the main entry point. It delegates to the shared retrieval
    lookup so every import path uses the same retry policy, provider
    fallback behavior, and address-confidence validation.

    Returns:
        PropertyRecord or None if no provider is registered or lookup fails.
    """
    from plotlot.retrieval.property import lookup_property as retrieval_lookup_property

    return cast(
        PropertyRecord | None,
        await retrieval_lookup_property(
            address,
            county,
            lat=lat,
            lng=lng,
            state=state,
        ),
    )


__all__ = [
    "PropertyProvider",
    "PropertyRecord",
    "get_provider",
    "lookup_property",
    "register_provider",
    "registered_counties",
]
