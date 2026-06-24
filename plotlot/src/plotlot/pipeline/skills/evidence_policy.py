"""Evidence-binding policy gate for load-bearing underwriting assumptions.

Ensures every load-bearing claim (rent, cap_rate, hard_cost, zoning) has either
evidence backing or an explicit override label before an analysis can execute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from plotlot.storage.models import AssumptionSet

LOAD_BEARING_CLAIMS: list[str] = ["rent", "cap_rate", "hard_cost", "zoning"]


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Result of an evidence-binding policy check."""

    blocked: bool
    message: str = ""


def check_evidence_binding(assumption_set: AssumptionSet) -> PolicyResult:
    """Check that all load-bearing claims have evidence or override labels.

    Args:
        assumption_set: The AssumptionSet to validate. Must have a labels_json
            dict mapping claim keys to label dicts with optional evidence_ids
            and override_label fields.

    Returns:
        PolicyResult(blocked=True, ...) if any load-bearing claim lacks both
        evidence_ids and an override_label. Returns PolicyResult(blocked=False)
        if all load-bearing claims pass.
    """
    labels: dict = cast(dict, assumption_set.labels_json)

    for claim_key in LOAD_BEARING_CLAIMS:
        claim_labels: dict = labels.get(claim_key, {})
        evidence_ids: list = claim_labels.get("evidence_ids", [])
        override_label: str = claim_labels.get("override_label", "")

        if evidence_ids or override_label:
            continue

        return PolicyResult(
            blocked=True,
            message=(
                f"Load-bearing assumption '{claim_key}' lacks evidence_ids and "
                f"override_label. Provide evidence or set an explicit override."
            ),
        )

    return PolicyResult(blocked=False)
