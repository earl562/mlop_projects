from __future__ import annotations

import json

from plotlot.cli_harness import main


def test_cli_municode_search_and_section_use_fixture_adapter(capsys) -> None:
    search_exit = main(["municode", "search", "--jurisdiction", "miami", "--query", "parking"])
    search_payload = json.loads(capsys.readouterr().out)
    section_id = search_payload["results"][0]["section_id"]

    section_exit = main(["municode", "section", "--section-id", section_id])
    section_payload = json.loads(capsys.readouterr().out)

    assert search_exit == 0
    assert section_exit == 0
    assert search_payload["source_mode"] == "fixture"
    assert search_payload["results"][0]["freshness_status"] == "requires_official_verification"
    assert section_payload["section"]["section_identifier"] == "Sec. 7.1.2.3"


def test_cli_municode_extract_rules_outputs_structured_rules(capsys) -> None:
    exit_code = main(
        ["municode", "extract-rules", "--section-id", "municode_miami_parking_fixture"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["rules"]["parking_spaces_per_dwelling_unit"] == 1.5
    assert payload["requires_official_verification"] is True
