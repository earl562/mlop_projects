"""Tests for the CLI harness entrypoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

from plotlot.cli import _harness_lookup, main
from plotlot.harness.contracts import SkillOutput


async def test_harness_lookup_invokes_runtime_and_prints_summary(monkeypatch, capsys) -> None:
    runtime = type("RuntimeStub", (), {})()
    runtime.run_skill = AsyncMock(
        return_value=SkillOutput(
            status="success",
            summary="Zoning research completed.",
            data={
                "report": {
                    "formatted_address": "123 Main St, Miami, FL",
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "zoning_district": "RU-1",
                    "zoning_description": "Single-Family Residential",
                    "allowed_uses": ["single-family"],
                }
            },
            evidence_ids=["ev_source_0"],
            next_actions=["review_evidence"],
        )
    )
    monkeypatch.setattr("plotlot.harness.bootstrap.build_default_runtime", lambda: runtime)

    await _harness_lookup("123 Main St")

    runtime.run_skill.assert_awaited_once()
    output = capsys.readouterr().out
    assert "PlotLot Harness Analysis" in output
    assert "RU-1" in output
    assert "ev_source_0" in output


def test_main_routes_harness_flag(monkeypatch) -> None:
    seen: dict[str, str] = {}

    async def fake_harness_lookup(address: str) -> None:
        seen["address"] = address

    monkeypatch.setattr("plotlot.cli._harness_lookup", fake_harness_lookup)
    monkeypatch.setattr("plotlot.cli.sys.argv", ["plotlot", "--harness", "123 Main St"])

    main()

    assert seen["address"] == "123 Main St"
