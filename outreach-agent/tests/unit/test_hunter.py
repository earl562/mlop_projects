"""Unit tests for Hunter.io domain lookup helper."""
from __future__ import annotations

import pytest
from outreach.tools.hunter import domain_from_company


def test_known_homebuilders():
    assert domain_from_company("D.R. Horton") == "drhorton.com"
    assert domain_from_company("dr horton") == "drhorton.com"
    assert domain_from_company("Lennar") == "lennar.com"
    assert domain_from_company("KB Home") == "kbhome.com"
    assert domain_from_company("Meritage") == "meritagehomes.com"
    assert domain_from_company("Taylor Morrison") == "taylormorrison.com"


def test_known_firms():
    assert domain_from_company("Valley Oak Partners") == "valleyoakpartners.com"
    assert domain_from_company("Tierra Energy") == "tierraenergy.com"
    assert domain_from_company("CBRE") == "cbre.com"


def test_unknown_company_returns_none():
    assert domain_from_company("Some Random LLC") is None
    assert domain_from_company("") is None


def test_case_insensitive():
    assert domain_from_company("LENNAR") == "lennar.com"
    assert domain_from_company("lennar") == "lennar.com"
    assert domain_from_company("Lennar") == "lennar.com"
