"""PostgreSQL-backed county schema registry (replaces Firestore cache).

Public interface mirrors storage/firestore.py so callers only need to change
their import path.
"""

from plotlot.property.schemas.registry import (
    get_county_cache,
    get_field_mapping,
    save_county_cache,
    save_field_mapping,
)

__all__ = [
    "get_county_cache",
    "get_field_mapping",
    "save_county_cache",
    "save_field_mapping",
]
