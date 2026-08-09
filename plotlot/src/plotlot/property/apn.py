"""Assessor Parcel Number parsing.

Vacant land frequently has no usable street address. Three separate parcels on
Pahvant St in Oceanside are all recorded as "0 PAHVANT ST", and a geocoder given
that string drops the "0" and returns the street centreline — so an
address-keyed lookup cannot identify which lot is meant, and silently probes a
point in the road.

The APN is the parcel's actual identifier, so it is accepted as an alternative
to an address wherever an address is taken.

Formats seen in the wild, all equivalent::

    1461210800
    146-121-08-00
    146 121 08 00
    APN 1461210800
    APN: 146-121-08-00
"""

from __future__ import annotations

import re

# County APNs run 8-14 digits (San Diego uses 10). Below 8 risks swallowing a
# ZIP code; above 14 is not a parcel number.
_MIN_DIGITS = 8
_MAX_DIGITS = 14

_APN_PREFIX_RE = re.compile(r"^\s*(?:apn|ap\s*n|parcel(?:\s*(?:no|number|#))?)\s*[:#]?\s*", re.I)

# Only separators a parcel number may contain — anything else means it is prose.
_SEPARATORS_RE = re.compile(r"^[\d\s\-.]+$")


def parse_apn(text: str) -> str | None:
    """Return the digits-only APN if `text` is a parcel number, else None.

    Conservative by design: a string is only treated as an APN when it consists
    solely of digits and separators (after an optional "APN" prefix). "1461210800"
    parses; "1461 Main St" does not, because a street name is not a separator.
    """
    if not text:
        return None

    candidate = _APN_PREFIX_RE.sub("", text.strip())
    had_prefix = candidate != text.strip()

    # Strip a trailing jurisdiction hint ("1461210800, San Diego, CA").
    candidate = candidate.split(",")[0].strip()
    if not candidate or not _SEPARATORS_RE.match(candidate):
        return None

    digits = re.sub(r"\D", "", candidate)
    if not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS):
        return None

    # A bare run of digits with no separators and no "APN" prefix is ambiguous
    # only below the parcel-number range, which the length check already excludes.
    _ = had_prefix
    return digits


def looks_like_apn(text: str) -> bool:
    """True when `text` should be resolved as a parcel number rather than geocoded."""
    return parse_apn(text) is not None


def format_apn(apn: str) -> str:
    """Group a 10-digit San Diego APN for display: 1461210800 -> 146-121-08-00."""
    digits = re.sub(r"\D", "", apn or "")
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:]}"
    return digits
