"""Tests for the non-Municode code-provider research harness."""

from __future__ import annotations

import json

import pytest

from plotlot.harness import code_provider_research


@pytest.mark.asyncio
async def test_run_research_retries_counties_with_empty_results(tmp_path, monkeypatch):
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "county": {"state": "CA", "county": "Yolo", "geoid": "06113"},
                        "municode_authorities": {"result_count": 0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    async def fake_call_discovery(adapter, *, county, state, timeout_seconds):  # noqa: ANN001, ARG001
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "success", "results": [], "message": None}
        return {
            "status": "success",
            "message": None,
            "results": [
                {
                    "platform": "amlegal",
                    "publisher": "American Legal Publishing",
                    "source_url": "https://codelibrary.amlegal.com/codes/yolocounty",
                    "confidence": "medium",
                }
            ],
        }

    monkeypatch.setattr(code_provider_research, "_call_discovery", fake_call_discovery)

    payload = await code_provider_research.run_research(
        coverage_path=coverage_path,
        concurrency=1,
        timeout_seconds=1,
        retry_misses=1,
    )

    assert calls == 2
    assert payload["summary"] == {"amlegal": 1}
    assert payload["results"][0]["provider_found"] is True
    assert payload["results"][0]["retry_round"] == 1
