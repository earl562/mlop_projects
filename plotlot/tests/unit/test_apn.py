"""Unit tests for APN parsing.

Vacant land is the case that needs this: three separate Oceanside parcels are
all recorded as "0 PAHVANT ST", so the address cannot select one of them.
"""

from __future__ import annotations

import pytest

from plotlot.property.apn import format_apn, looks_like_apn, parse_apn


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1461210800", "1461210800"),
        ("146-121-08-00", "1461210800"),
        ("146 121 08 00", "1461210800"),
        ("146.121.08.00", "1461210800"),
        ("APN 1461210800", "1461210800"),
        ("apn: 146-121-08-00", "1461210800"),
        ("Parcel # 1461210800", "1461210800"),
        ("  1461210800  ", "1461210800"),
        ("1461210800, San Diego, CA", "1461210800"),
    ],
)
def test_parses_apn_forms(text: str, expected: str) -> None:
    assert parse_apn(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "0 Pahvant St, Oceanside, CA 92054",
        "1233 Hueneme St, San Diego, CA",
        "2514 Pahvant St",
        "92054",  # ZIP — too short to be a parcel number
        "12345",
        "",
        "   ",
        "Oceanside",
        "1461 Main Street",  # leading digits, but a street name follows
    ],
)
def test_rejects_addresses_and_short_numbers(text: str) -> None:
    assert parse_apn(text) is None
    assert looks_like_apn(text) is False


def test_rejects_numbers_outside_the_parcel_range() -> None:
    assert parse_apn("1234567") is None  # 7 digits
    assert parse_apn("123456789012345") is None  # 15 digits


def test_looks_like_apn_agrees_with_parse() -> None:
    assert looks_like_apn("1461210800") is True
    assert looks_like_apn("146-121-08-00") is True


def test_format_apn_groups_san_diego_numbers() -> None:
    assert format_apn("1461210800") == "146-121-08-00"
    assert format_apn("146-121-08-00") == "146-121-08-00"


def test_format_apn_leaves_other_lengths_as_digits() -> None:
    assert format_apn("12345678") == "12345678"
    assert format_apn("") == ""
