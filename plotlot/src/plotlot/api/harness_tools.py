from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import ExecutionMode, JsonObject, RunId, SourceMode, ToolCall
from plotlot.harness.full_harness_registry import (
    RegistryLookupError,
    get_tool_spec,
    list_tool_specs,
)
from plotlot.harness.run_store import HarnessRunNotFoundError, default_harness_run_store
from plotlot.harness.tool_call_store import default_tool_call_ledger, tool_call_from_result
from plotlot.harness.tool_router import (
    HarnessToolCallRequest,
    HarnessToolCallResult,
    default_tool_router,
)
from plotlot.storage.db import get_session
from plotlot.storage.models import ApprovalRequest

router = APIRouter(prefix="/api/v1", tags=["harness-tools"])

_FIXTURE_ONLY_TOOL_NAMES = frozenset(
    {
        "search_municode",
        "get_municode_section",
        "extract_ordinance_rules",
        "search_south_florida_gis",
        "discover_rehabvaluator_video_sections",
    }
)


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    actor_user_id: str = Field(default="api", min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    site_id: str | None = Field(default=None, min_length=1)
    args: JsonObject = Field(default_factory=dict)
    source_mode: SourceMode = SourceMode.FIXTURE
    risk_budget_cents: int = Field(default=0, ge=0)
    live_network_allowed: bool = False
    approved_approval_ids: list[str] = Field(default_factory=list)


@router.get("/harness/tools")
async def harness_tools() -> JsonObject:
    return {"tools": [tool.model_dump(mode="json") for tool in list_tool_specs()]}


@router.get("/harness/tools/{tool_name}")
async def harness_tool(tool_name: str) -> JsonObject:
    try:
        return {"tool": get_tool_spec(tool_name).model_dump(mode="json")}
    except RegistryLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/harness/tools/{tool_name}/call", response_model=None)
async def harness_tool_call(tool_name: str, body: ToolCallRequest) -> JsonObject | JSONResponse:
    _require_supported_source_mode(tool_name=tool_name, source_mode=body.source_mode)
    validated_approval_ids = await _validated_approved_ids(
        approval_ids=set(body.approved_approval_ids),
        workspace_id=body.workspace_id,
    )
    result = await default_tool_router().call_async(
        HarnessToolCallRequest(
            tool_name=tool_name,
            args=body.args,
            context=ToolContext(
                workspace_id=body.workspace_id,
                actor_user_id=body.actor_user_id,
                run_id=body.run_id,
                project_id=body.project_id,
                site_id=body.site_id,
                risk_budget_cents=body.risk_budget_cents,
                live_network_allowed=body.live_network_allowed,
                approved_approval_ids=validated_approval_ids,
            ),
            source_mode=body.source_mode,
            execution_mode=ExecutionMode.API,
        )
    )
    tool_call = _persist_tool_result(result)
    payload = result.model_dump(mode="json")
    payload["tool_call_id"] = str(tool_call.tool_call_id)
    if result.ok:
        return payload
    return JSONResponse(status_code=_tool_result_status_code(result.status.value), content=payload)


@router.get("/harness/runs/{run_id}/tool-calls")
async def harness_run_tool_calls(run_id: str) -> JsonObject:
    tool_calls = default_tool_call_ledger().list_tool_calls(run_id=RunId(run_id))
    return {"tool_calls": [item.model_dump(mode="json") for item in tool_calls]}


def _persist_tool_result(result: HarnessToolCallResult) -> ToolCall:
    tool_call = default_tool_call_ledger().save_tool_call(tool_call_from_result(result))
    try:
        default_harness_run_store().append_events(result.run_id, result.events)
    except HarnessRunNotFoundError:
        pass
    return tool_call


async def _validated_approved_ids(
    *,
    approval_ids: set[str],
    workspace_id: str,
) -> set[str]:
    if not approval_ids:
        return set()

    session = await get_session()
    try:
        now = datetime.now(timezone.utc)
        approved: set[str] = set()
        for approval_id in approval_ids:
            row = await session.get(ApprovalRequest, approval_id)
            if (
                row is not None
                and row.workspace_id == workspace_id
                and row.status == "approved"
                and (row.expires_at is None or row.expires_at > now)
            ):
                approved.add(approval_id)
        return approved
    except Exception:
        return set()
    finally:
        await session.close()


def _require_supported_source_mode(*, tool_name: str, source_mode: SourceMode) -> None:
    if source_mode is SourceMode.FIXTURE:
        return
    if tool_name not in _FIXTURE_ONLY_TOOL_NAMES:
        return
    raise HTTPException(
        status_code=501,
        detail="Only fixture source mode is wired for this harness tool",
    )


def _tool_result_status_code(status: str) -> int:
    match status:
        case "approval_required":
            return 409
        case "denied":
            return 403
        case "failed":
            return 422
        case _:
            return 500
