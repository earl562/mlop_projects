"""Tests for the committed property-only Drive evaluation corpus."""

from __future__ import annotations

import json
from pathlib import Path

from plotlot.evaluation.leads import (
    LeadFixtureManifest,
    assert_fixture_is_sanitized,
    load_lead_fixture,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "leads"
FIXTURE_PATH = FIXTURE_DIR / "plotlot_drive_leads.json"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def test_drive_fixture_is_sanitized_unique_and_market_representative():
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert_fixture_is_sanitized(raw)
    cases = load_lead_fixture(FIXTURE_PATH)

    assert len(cases) == 16
    assert len({case.case_id for case in cases}) == len(cases)
    assert len(
        {(case.address.casefold(), case.city, case.state) for case in cases}
    ) == len(cases)
    assert {(case.county, case.state) for case in cases} == {
        ("Broward", "FL"),
        ("Miami-Dade", "FL"),
        ("Palm Beach", "FL"),
        ("Mecklenburg", "NC"),
        ("San Diego", "CA"),
    }


def test_drive_fixture_manifest_matches_committed_cases():
    manifest = LeadFixtureManifest.model_validate_json(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    cases = load_lead_fixture(FIXTURE_PATH)

    assert manifest.schema_version == "1.0"
    assert manifest.case_count == len(cases)
    assert set(manifest.markets) == {
        "Broward, FL",
        "Miami-Dade, FL",
        "Palm Beach, FL",
        "Mecklenburg, NC",
        "San Diego, CA",
    }
    assert all(
        source["source_file_id"].startswith("drive_sha256:")
        for source in manifest.source_files
    )
