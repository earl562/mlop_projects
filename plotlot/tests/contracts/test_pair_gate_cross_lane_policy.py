from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ci"))

from pair_gate_checks import parse_report, verify_test_policy_bindings
from pair_gate_test_policy import BYRIGHT_DEFERRED_TESTS, BYRIGHT_SEPARATELY_REQUIRED_TESTS
from pair_gate_types import GateError


SEPARATELY_REQUIRED_TITLE = BYRIGHT_SEPARATELY_REQUIRED_TESTS[0][0]


def _write_report(
    path: Path,
    assertions: list[dict[str, object]],
    *,
    total: int,
    pending: int,
) -> None:
    path.write_text(
        json.dumps(
            {
                "numTotalTests": total,
                "numPendingTests": pending,
                "testResults": [{"assertionResults": assertions}],
            }
        )
    )


def _assertion(title: str, status: str) -> dict[str, object]:
    ancestor, test_title = title.split(" > ", maxsplit=1)
    return {"ancestorTitles": [ancestor], "title": test_title, "status": status}


def test_exact_deferred_and_separately_required_reports_are_accepted(tmp_path: Path) -> None:
    general = tmp_path / "general.json"
    persistence = tmp_path / "persistence.json"
    deferred = [title for title, _ in BYRIGHT_DEFERRED_TESTS]
    _write_report(
        general,
        [_assertion(title, "skipped") for title in [*deferred, SEPARATELY_REQUIRED_TITLE]],
        total=506,
        pending=11,
    )
    _write_report(
        persistence,
        [_assertion(SEPARATELY_REQUIRED_TITLE, "passed")],
        total=7,
        pending=0,
    )

    assert parse_report(
        {
            "format": "vitest",
            "path": general.name,
            "deferredSkippedTests": deferred,
            "separatelyRequiredTests": [SEPARATELY_REQUIRED_TITLE],
        },
        tmp_path,
    ) == (495, 0)
    assert parse_report(
        {
            "format": "vitest",
            "path": persistence.name,
            "requiredPassedTests": [SEPARATELY_REQUIRED_TITLE],
        },
        tmp_path,
    ) == (7, 0)


def test_unclassified_general_suite_skip_is_rejected(tmp_path: Path) -> None:
    report = tmp_path / "general.json"
    deferred = [title for title, _ in BYRIGHT_DEFERRED_TESTS]
    assertions = [_assertion(title, "skipped") for title in [*deferred, SEPARATELY_REQUIRED_TITLE]]
    assertions.append(_assertion("unexpected integration > silently skipped", "skipped"))
    _write_report(report, assertions, total=507, pending=12)

    with pytest.raises(GateError) as raised:
        parse_report(
            {
                "format": "vitest",
                "path": report.name,
                "deferredSkippedTests": deferred,
                "separatelyRequiredTests": [SEPARATELY_REQUIRED_TITLE],
            },
            tmp_path,
        )

    assert raised.value.code == "PAIR_E_SKIPPED_TEST"


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (None, "PAIR_E_STALE_EVIDENCE"),
        ("failed", "PAIR_E_STALE_EVIDENCE"),
        ("skipped", "PAIR_E_SKIPPED_TEST"),
    ],
)
def test_separately_required_test_must_pass(
    tmp_path: Path,
    status: str | None,
    expected_code: str,
) -> None:
    report = tmp_path / "persistence.json"
    assertions = [] if status is None else [_assertion(SEPARATELY_REQUIRED_TITLE, status)]
    _write_report(report, assertions, total=7, pending=int(status == "skipped"))

    with pytest.raises(GateError) as raised:
        parse_report(
            {
                "format": "vitest",
                "path": report.name,
                "requiredPassedTests": [SEPARATELY_REQUIRED_TITLE],
            },
            tmp_path,
        )

    assert raised.value.code == expected_code


def test_separately_required_manifest_binding_must_match_lane() -> None:
    gate = {
        "testPolicy": {
            "byrightSeparatelyRequiredTests": [
                {
                    "title": SEPARATELY_REQUIRED_TITLE,
                    "lane": "byright-persistence",
                    "releaseStatus": "required",
                }
            ]
        },
        "lanes": [
            {
                "id": "byright-persistence",
                "report": {"format": "vitest", "path": "report.json", "requiredPassedTests": []},
            },
            {
                "id": "byright-vitest",
                "report": {
                    "format": "vitest",
                    "path": "general.json",
                    "separatelyRequiredTests": [SEPARATELY_REQUIRED_TITLE],
                },
            },
        ],
    }

    with pytest.raises(GateError) as raised:
        verify_test_policy_bindings(gate)

    assert raised.value.code == "PAIR_E_MANIFEST"
