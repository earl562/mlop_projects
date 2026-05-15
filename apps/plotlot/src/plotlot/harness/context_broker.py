"""Context selection for harness runs."""

from __future__ import annotations

from dataclasses import asdict

from plotlot.harness.contracts import HarnessContext


class ContextBroker:
    """Builds the minimal structured context required for a skill run."""

    def build(self, context: HarnessContext) -> dict:
        return {k: v for k, v in asdict(context).items() if v is not None}
