from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from pydantic import Field

from plotlot.harness.approval_store import LocalApprovalLedger, default_approval_ledger
from plotlot.harness.contracts import JsonObject, RunId, SourceMode
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.evidence_store import LocalEvidenceLedger, default_evidence_ledger
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger
from plotlot.harness.run_store import LocalHarnessRunStore, default_harness_run_store
from plotlot.harness.tool_call_store import LocalToolCallLedger, default_tool_call_ledger
from plotlot.harness.verification_store import (
    LocalVerificationLedger,
    default_verification_ledger,
)


class TuiScreenName(StrEnum):
    HOME = "home"
    RUN_MONITOR = "run_monitor"
    EVIDENCE = "evidence"
    VERIFICATION = "verification"
    APPROVALS = "approvals"
    REPORT = "report"
    REPLAY_DEBUG = "replay_debug"
    SOURCE_CATALOG = "source_catalog"
    TRAINING = "training"


class TuiPanel(HarnessContract):
    title: str = Field(min_length=1)
    items: list[JsonObject] = Field(default_factory=list)


class TuiScreen(HarnessContract):
    screen: TuiScreenName
    title: str = Field(min_length=1)
    summary: JsonObject = Field(default_factory=dict)
    panels: list[TuiPanel] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class TuiRenderRequest(HarnessContract):
    screen: TuiScreenName = TuiScreenName.HOME
    run_id: RunId | None = None
    source_mode: SourceMode = SourceMode.FIXTURE

    def required_run_id(self) -> RunId:
        if self.run_id is None:
            raise TuiRunRequiredError(screen=self.screen)
        return self.run_id


@dataclass(frozen=True, slots=True)
class TuiStores:
    run_store: LocalHarnessRunStore
    evidence_ledger: LocalEvidenceLedger
    report_ledger: LocalReportLedger
    verification_ledger: LocalVerificationLedger
    tool_call_ledger: LocalToolCallLedger
    approval_ledger: LocalApprovalLedger


@dataclass(frozen=True, slots=True)
class TuiRunRequiredError(Exception):
    screen: TuiScreenName

    def __str__(self) -> str:
        return f"TUI screen {self.screen.value!r} requires --run-id"


def default_tui_stores() -> TuiStores:
    return TuiStores(
        run_store=default_harness_run_store(),
        evidence_ledger=default_evidence_ledger(),
        report_ledger=default_report_ledger(),
        verification_ledger=default_verification_ledger(),
        tool_call_ledger=default_tool_call_ledger(),
        approval_ledger=default_approval_ledger(),
    )


def render_tui_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    from plotlot.harness.tui_approvals import approval_list_screen
    from plotlot.harness.tui_home import home_screen
    from plotlot.harness.tui_inspection import (
        evidence_screen,
        report_screen,
        run_monitor_screen,
        source_catalog_screen,
        training_screen,
        verification_screen,
    )
    from plotlot.harness.tui_replay_debug import replay_debug_screen

    match request.screen:
        case TuiScreenName.HOME:
            return home_screen(request, stores)
        case TuiScreenName.RUN_MONITOR:
            return run_monitor_screen(request, stores)
        case TuiScreenName.EVIDENCE:
            return evidence_screen(request, stores)
        case TuiScreenName.VERIFICATION:
            return verification_screen(request, stores)
        case TuiScreenName.APPROVALS:
            return approval_list_screen(request, stores.approval_ledger)
        case TuiScreenName.REPORT:
            return report_screen(request, stores)
        case TuiScreenName.REPLAY_DEBUG:
            return replay_debug_screen(request)
        case TuiScreenName.SOURCE_CATALOG:
            return source_catalog_screen(request)
        case TuiScreenName.TRAINING:
            return training_screen(request)
        case unreachable:
            assert_never(unreachable)


def format_tui_screen(screen: TuiScreen) -> str:
    lines = [screen.title, "=" * len(screen.title), ""]
    lines.extend(f"{key}: {value}" for key, value in screen.summary.items())
    for panel in screen.panels:
        lines.extend(["", panel.title, "-" * len(panel.title)])
        if panel.items:
            lines.extend(_format_panel_item(item) for item in panel.items)
        else:
            lines.append("(empty)")
    if screen.commands:
        lines.extend(["", "Commands", "--------"])
        lines.extend(screen.commands)
    return "\n".join(lines) + "\n"


def _format_panel_item(item: JsonObject) -> str:
    identity = item.get("run_id") or item.get("report_id") or item.get("evidence_id")
    identity = identity or item.get("verification_id") or item.get("tool_call_id")
    identity = identity or item.get("source_id") or item.get("video_source_id")
    return str(identity or item)
