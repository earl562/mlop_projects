from __future__ import annotations

import sys

from plotlot.config import settings
from plotlot.harness.browser_comp_capture import (
    BrowserCompCaptureSubject,
    capture_public_listing_comps,
)
from plotlot.harness.contracts import SourceMode


def _subject() -> BrowserCompCaptureSubject:
    return BrowserCompCaptureSubject(
        address="45 NW 209 ST, Miami Gardens, FL 33169",
        county="Miami-Dade",
        municipality="Miami Gardens",
        lot_size_sqft=10105.0,
        zoning_code="R-1",
    )


def test_browser_comp_capture_runner_accepts_command_with_arguments(tmp_path, monkeypatch) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import sys",
                "payload = json.loads(sys.stdin.read())",
                "print(json.dumps({",
                '    "status": "success",',
                '    "strategy": "public_sold_listing_capture",',
                '    "candidates": [{',
                '        "title": "Runner Candidate",',
                '        "url": "https://www.zillow.com/homedetails/runner",',
                '        "address_hint": payload["address"],',
                '        "classification": "likely_vacant_land"',
                "    }],",
                '    "warnings": []',
                "}))",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings,
        "browser_comp_runner_command",
        f"{sys.executable} {runner}",
    )

    result = capture_public_listing_comps(_subject(), source_mode=SourceMode.LIVE)

    assert result.payload["status"] == "success"
    assert result.payload["provider"] == "browser_use"
    assert result.payload["candidates"][0]["title"] == "Runner Candidate"
    assert result.payload["candidates"][0]["address_hint"] == (
        "45 NW 209 ST, Miami Gardens, FL 33169"
    )


def test_browser_comp_capture_normalizes_sparse_zillow_runner_candidates(
    tmp_path, monkeypatch
) -> None:
    runner = tmp_path / "sparse_runner.py"
    runner.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "print(json.dumps({",
                '    "status": "success",',
                '    "candidates": [',
                "        {",
                '            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",',
                '            "url": "https://www.zillow.com/homedetails/17605-NW-19th-Ave-Miami-Gardens-FL-33056/44106704_zpid/",',
                '            "description": "Sold vacant lot in Miami Gardens."',
                "        },",
                "        {",
                '            "title": "2940 NW 169th Ter, Miami Gardens, FL 33056 | Zillow",',
                '            "url": "https://www.zillow.com/homedetails/2940-NW-169th-Ter-Miami-Gardens-FL-33056/455424748_zpid/",',
                '            "description": "Public sold land page."',
                "        },",
                "        {",
                '            "title": "168 Terrace, Miami Gardens, FL 33056 | Zillow",',
                '            "url": "https://www.zillow.com/homedetails/168-Terrace-Miami-Gardens-FL-33056/443486566_zpid/",',
                '            "description": "Sold residential lot."',
                "        }",
                "    ],",
                '    "warnings": []',
                "}))",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "browser_comp_runner_command", f"{sys.executable} {runner}")

    result = capture_public_listing_comps(_subject(), source_mode=SourceMode.LIVE)

    candidates = result.payload["candidates"]
    assert result.payload["status"] == "success"
    assert {candidate["address_hint"] for candidate in candidates} == {
        "17605 NW 19th Avenue, Miami Gardens, FL 33056",
        "2940 NW 169th Ter, Miami Gardens, FL 33056",
        "168 Terrace, Miami Gardens, FL 33056",
    }
    assert {candidate["classification"] for candidate in candidates} == {"likely_vacant_land"}
    assert {candidate["source_domain"] for candidate in candidates} == {"www.zillow.com"}
    assert all(candidate["municipality_match"] is True for candidate in candidates)
    assert all(candidate["search_category"] == "sold_land" for candidate in candidates)
    assert all(
        candidate["candidate_kind"] == "browser_listing_candidate" for candidate in candidates
    )


def test_browser_comp_capture_returns_error_when_runner_command_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "browser_comp_runner_command", "plotlot-missing-runner")

    result = capture_public_listing_comps(_subject(), source_mode=SourceMode.LIVE)

    assert result.payload["status"] == "error"
    assert result.payload["provider"] == "browser_use"
    assert result.payload["candidates"] == []
    assert "not found" in result.payload["warnings"][0].lower()


def test_browser_comp_capture_returns_error_when_runner_times_out(tmp_path, monkeypatch) -> None:
    runner = tmp_path / "slow_runner.py"
    runner.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import time",
                "time.sleep(10)",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "browser_comp_runner_command", f"{sys.executable} {runner}")
    monkeypatch.setattr(settings, "browser_comp_runner_timeout_seconds", 0.01)

    result = capture_public_listing_comps(_subject(), source_mode=SourceMode.LIVE)

    assert result.payload["status"] == "error"
    assert result.payload["provider"] == "browser_use"
    assert result.payload["candidates"] == []
    assert "timed out" in result.payload["warnings"][0].lower()
