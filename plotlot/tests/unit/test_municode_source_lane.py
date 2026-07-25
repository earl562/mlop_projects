from __future__ import annotations

from plotlot.harness.contracts import FreshnessStatus, SourceMode
from plotlot.harness.municode_source import (
    create_municode_evidence,
    extract_ordinance_rules,
    get_municode_section,
    load_municode_source_catalog,
    search_municode,
)


def test_municode_fixture_search_returns_florida_section_with_caveat() -> None:
    results = search_municode(
        jurisdiction="miami",
        query="parking",
        source_mode=SourceMode.FIXTURE,
    )

    assert results[0].jurisdiction == "City of Miami"
    assert results[0].provider == "municode"
    assert results[0].freshness_status == FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION
    assert "official municipal verification" in results[0].official_verification_note


def test_municode_fixture_section_extracts_structured_rules() -> None:
    section = get_municode_section("municode_miami_parking_fixture", source_mode=SourceMode.FIXTURE)
    rules = extract_ordinance_rules(section)

    assert section.section_identifier == "Sec. 7.1.2.3"
    assert rules.source_section_id == section.section_id
    assert rules.rules["parking_spaces_per_dwelling_unit"] == 1.5
    assert rules.requires_official_verification is True


def test_municode_fixture_section_creates_ordinance_evidence() -> None:
    section = get_municode_section("municode_miami_parking_fixture", source_mode=SourceMode.FIXTURE)
    evidence = create_municode_evidence(section, run_id="run_fixture_municode")

    assert evidence.evidence_id == "ev_run_fixture_municode_municode_miami_parking_fixture"
    assert evidence.source_type == "municode_section"
    assert evidence.freshness_status == "requires_official_verification"
    assert evidence.source_mode == SourceMode.FIXTURE
    assert evidence.metadata["provider"] == "municode"


def test_municode_fixture_source_catalog_entries_are_ordinance_sources() -> None:
    catalog = load_municode_source_catalog(SourceMode.FIXTURE)

    assert catalog[0].lane == "ordinance_code"
    assert catalog[0].provider == "municode"
    assert catalog[0].metadata["official_verification_note"]
