"""Property provider package — abstract interface + per-county implementations.

Usage::

    from plotlot.property import lookup_property, PropertyProvider, PropertyRecord

    record = await lookup_property("171 NE 209th Ter, Miami, FL", "Miami-Dade", lat=25.9, lng=-80.2)

Adding a new county is three steps:
  1. Create ``plotlot/property/<county>.py`` with a :class:`PropertyProvider` subclass.
  2. Register it below (or call :func:`register_provider` at startup).
  3. Done — ``lookup_property`` routes to it automatically.
"""

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.property.registry import get_provider, register_provider, registered_counties

# Register built-in providers ---------------------------------------------------

from plotlot.property.broward import BrowardProvider
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

# NC providers
_mecklenburg = MecklenburgProvider()

register_provider("mecklenburg", _mecklenburg)


# Convenience top-level lookup ---------------------------------------------------


async def lookup_property(
    address: str,
    county: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> PropertyRecord | None:
    """Look up property data via the registered provider for *county*.

    This is the main entry point. It delegates to the appropriate
    :class:`PropertyProvider` based on the county name.

    Returns:
        PropertyRecord or None if no provider is registered or lookup fails.
    """
    provider = get_provider(county)
    if provider is None:
        import logging

        logging.getLogger(__name__).warning(
            "No PropertyProvider registered for county: %s",
            county,
        )
        return None

    try:
        return await provider.lookup(address, county, lat=lat, lng=lng)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "PropertyProvider.lookup failed for %s (%s)",
            address,
            county,
        )
        return None


__all__ = [
    "PropertyProvider",
    "PropertyRecord",
    "get_provider",
    "lookup_property",
    "register_provider",
    "registered_counties",
]
