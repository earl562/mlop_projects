from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

import anyio
from pydantic import Field, TypeAdapter, ValidationError

from plotlot.domain.types import PolicyDecision, ToolContext
from plotlot.harness.contracts import (
    ExecutionMode,
    JsonObject,
    PlotLotEvent,
    PlotLotEventError,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RunId,
    SourceMode,
    ToolCallId,
    WorkspaceId,
)
from plotlot.harness.contracts.base import EventId, HarnessContract
from plotlot.harness.full_harness_registry import RegistryLookupError, get_tool_spec
from plotlot.harness.municode_source import (
    MunicodeModeUnsupportedError,
    MunicodeSectionNotFoundError,
)
from plotlot.harness.policy import HarnessPolicyEngine, HarnessPolicyRequest
from plotlot.harness.report_store import ReportNotFoundError
from plotlot.harness.tool_router_handlers import ToolHandler, default_tool_handlers

JsonObjectAdapter = TypeAdapter(JsonObject)


class ToolRouteStatus(StrEnum):
    COMPLETED = "completed"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    FAILED = "failed"


class HarnessToolCallRequest(HarnessContract):
    tool_name: str = Field(min_length=1)
    args: JsonObject = Field(default_factory=dict)
    context: ToolContext
    source_mode: SourceMode = SourceMode.FIXTURE
    execution_mode: ExecutionMode = ExecutionMode.LOCAL
    approval_id: str | None = None


class HarnessToolCallResult(HarnessContract):
    ok: bool
    tool_call_id: ToolCallId
    tool_name: str = Field(min_length=1)
    run_id: RunId
    args: JsonObject = Field(default_factory=dict)
    status: ToolRouteStatus
    policy_decision: PolicyDecision
    payload: JsonObject = Field(default_factory=dict)
    events: list[PlotLotEvent]
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: PlotLotEventError | None = None
    source_mode: SourceMode


class ToolEventDraft(HarnessContract):
    request: HarnessToolCallRequest
    sequence: int = Field(ge=1)
    event_type: PlotLotEventType
    source: PlotLotEventSource
    status: PlotLotEventStatus
    payload: JsonObject
    error: PlotLotEventError | None = None


class HarnessToolRouter:
    def __init__(
        self,
        *,
        policy: HarnessPolicyEngine | None = None,
        handlers: dict[str, ToolHandler] | None = None,
    ) -> None:
        self._policy = policy or HarnessPolicyEngine()
        self._handlers = handlers or default_tool_handlers()

    async def call_async(self, request: HarnessToolCallRequest) -> HarnessToolCallResult:
        events = [_event(_requested_event(request))]
        try:
            tool_spec = get_tool_spec(request.tool_name)
        except RegistryLookupError as exc:
            error = PlotLotEventError(code="tool_not_registered", message=str(exc))
            events.append(_event(_failed_event(request, len(events) + 1, error)))
            return _result(
                request, False, ToolRouteStatus.FAILED, _blocked(str(exc)), events, error=error
            )

        decision = self._policy.authorize_tool_spec(
            HarnessPolicyRequest(
                tool_spec=tool_spec,
                context=request.context,
                approval_id=request.approval_id,
            )
        )
        events.append(_event(_policy_event(request, len(events) + 1, decision)))
        if decision.approval_required:
            events.append(_event(_approval_event(request, len(events) + 1, decision)))
            return _result(request, False, ToolRouteStatus.APPROVAL_REQUIRED, decision, events)
        if not decision.allowed:
            events.append(_event(_denied_event(request, len(events) + 1, decision)))
            return _result(request, False, ToolRouteStatus.DENIED, decision, events)

        handler = self._handlers.get(request.tool_name)
        if handler is None:
            error = PlotLotEventError(
                code="tool_handler_unavailable",
                message=f"No handler registered for {request.tool_name}",
            )
            events.append(_event(_failed_event(request, len(events) + 1, error)))
            return _result(request, False, ToolRouteStatus.FAILED, decision, events, error=error)
        events.append(_event(_started_event(request, len(events) + 1)))
        try:
            payload = await handler(request)
        except (
            ValidationError,
            MunicodeModeUnsupportedError,
            MunicodeSectionNotFoundError,
            ReportNotFoundError,
        ) as exc:
            error = PlotLotEventError(code="tool_call_failed", message=str(exc))
            events.append(_event(_failed_event(request, len(events) + 1, error)))
            return _result(request, False, ToolRouteStatus.FAILED, decision, events, error=error)
        events.append(_event(_completed_event(request, len(events) + 1)))
        return _result(request, True, ToolRouteStatus.COMPLETED, decision, events, payload=payload)

    def call(self, request: HarnessToolCallRequest) -> HarnessToolCallResult:
        return anyio.run(self.call_async, request)


def default_tool_router() -> HarnessToolRouter:
    return HarnessToolRouter()


def _result(
    request: HarnessToolCallRequest,
    ok: bool,
    status: ToolRouteStatus,
    decision: PolicyDecision,
    events: list[PlotLotEvent],
    *,
    payload: JsonObject | None = None,
    error: PlotLotEventError | None = None,
) -> HarnessToolCallResult:
    result_payload = payload or {}
    return HarnessToolCallResult(
        ok=ok,
        tool_call_id=ToolCallId(f"tool_call_{uuid4().hex[:12]}"),
        tool_name=request.tool_name,
        run_id=RunId(request.context.run_id),
        args=request.args,
        status=status,
        policy_decision=decision,
        payload=result_payload,
        events=events,
        evidence_ids=_evidence_ids(result_payload),
        error=error,
        source_mode=request.source_mode,
    )


def _requested_event(request: HarnessToolCallRequest) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=1,
        event_type=PlotLotEventType.TOOL_REQUESTED,
        source=PlotLotEventSource.TOOL,
        status=PlotLotEventStatus.PENDING,
        payload=JsonObjectAdapter.validate_python(
            {"tool_name": request.tool_name, "arg_keys": sorted(request.args)}
        ),
    )


def _policy_event(
    request: HarnessToolCallRequest,
    sequence: int,
    decision: PolicyDecision,
) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_POLICY_CHECKED,
        source=PlotLotEventSource.POLICY,
        status=PlotLotEventStatus.COMPLETED,
        payload={
            "tool_name": request.tool_name,
            "policy_decision": JsonObjectAdapter.validate_python(decision.model_dump(mode="json")),
        },
    )


def _approval_event(
    request: HarnessToolCallRequest,
    sequence: int,
    decision: PolicyDecision,
) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_APPROVAL_REQUIRED,
        source=PlotLotEventSource.POLICY,
        status=PlotLotEventStatus.PENDING,
        payload={"tool_name": request.tool_name, "approval_id": decision.approval_id or ""},
    )


def _denied_event(
    request: HarnessToolCallRequest,
    sequence: int,
    decision: PolicyDecision,
) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_DENIED,
        source=PlotLotEventSource.POLICY,
        status=PlotLotEventStatus.FAILED,
        payload={"tool_name": request.tool_name, "reason": decision.reason},
    )


def _started_event(request: HarnessToolCallRequest, sequence: int) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_STARTED,
        source=PlotLotEventSource.TOOL,
        status=PlotLotEventStatus.PENDING,
        payload={"tool_name": request.tool_name},
    )


def _completed_event(request: HarnessToolCallRequest, sequence: int) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_COMPLETED,
        source=PlotLotEventSource.TOOL,
        status=PlotLotEventStatus.COMPLETED,
        payload={"tool_name": request.tool_name},
    )


def _failed_event(
    request: HarnessToolCallRequest,
    sequence: int,
    error: PlotLotEventError,
) -> ToolEventDraft:
    return ToolEventDraft(
        request=request,
        sequence=sequence,
        event_type=PlotLotEventType.TOOL_FAILED,
        source=PlotLotEventSource.TOOL,
        status=PlotLotEventStatus.FAILED,
        payload={"tool_name": request.tool_name},
        error=error,
    )


def _event(draft: ToolEventDraft) -> PlotLotEvent:
    return PlotLotEvent(
        event_id=EventId(f"evt_{uuid4().hex[:12]}"),
        run_id=RunId(draft.request.context.run_id),
        workspace_id=WorkspaceId(draft.request.context.workspace_id),
        sequence=draft.sequence,
        type=draft.event_type,
        payload=draft.payload,
        source=draft.source,
        status=draft.status,
        source_mode=draft.request.source_mode,
        execution_mode=draft.request.execution_mode,
        error=draft.error,
    )


def _evidence_ids(payload: JsonObject) -> list[str]:
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list):
        return []

    evidence_ids: list[str] = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id") or item.get("id")
        if isinstance(evidence_id, str) and evidence_id:
            evidence_ids.append(evidence_id)
    return evidence_ids


def _blocked(reason: str) -> PolicyDecision:
    return PolicyDecision(allowed=False, reason=reason)
