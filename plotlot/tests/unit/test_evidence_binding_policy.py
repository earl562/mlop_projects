"""Unit tests for evidence-binding policy gate."""

from plotlot.pipeline.skills.evidence_policy import (
    LOAD_BEARING_CLAIMS,
    check_evidence_binding,
)


class FakeAssumptionSet:
    """Minimal stand-in for AssumptionSet ORM model — avoids DB dependency."""

    def __init__(self, labels_json: dict | None = None) -> None:
        self.labels_json = labels_json or {}


def test_409_on_missing_evidence() -> None:
    """Policy blocks when a load-bearing claim lacks both evidence_ids and override_label."""
    assumption_set = FakeAssumptionSet(labels_json={})  # No claims have evidence
    result = check_evidence_binding(assumption_set)
    assert result.blocked is True
    assert "rent" in result.message  # First load-bearing claim in the list


def test_pass_with_override_label() -> None:
    """Policy passes when load-bearing claims have override_label but no evidence_ids."""
    labels = {}
    for claim in LOAD_BEARING_CLAIMS:
        labels[claim] = {"override_label": "MANUAL_OVERRIDE", "evidence_ids": []}
    assumption_set = FakeAssumptionSet(labels_json=labels)
    result = check_evidence_binding(assumption_set)
    assert result.blocked is False


def test_pass_with_evidence_ids() -> None:
    """Policy passes when load-bearing claims have evidence_ids."""
    labels = {}
    for claim in LOAD_BEARING_CLAIMS:
        labels[claim] = {"evidence_ids": ["ev-1"], "override_label": ""}
    assumption_set = FakeAssumptionSet(labels_json=labels)
    result = check_evidence_binding(assumption_set)
    assert result.blocked is False
