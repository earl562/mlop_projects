from __future__ import annotations

import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol, TypeAlias, TypeGuard, cast

import anyio
from pydantic import Field, TypeAdapter

from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import (
    ExecutionMode,
    JsonObject,
    RunId,
    SourceMode,
)
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.cost_assumption_source import load_cost_assumption_source_catalog
from plotlot.harness.evidence_store import default_evidence_ledger
from plotlot.harness.full_harness_registry import list_skill_specs, list_tool_specs
from plotlot.harness.municode_source import load_municode_source_catalog
from plotlot.harness.report_store import default_report_ledger
from plotlot.harness.run_store import default_harness_run_store
from plotlot.harness.south_florida_gis import load_south_florida_gis_source_catalog
from plotlot.harness.tool_router import (
    HarnessToolCallRequest,
    HarnessToolCallResult,
    default_tool_router,
)
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.harness.verification_store import default_verification_ledger

JSON_OBJECT_ADAPTER = TypeAdapter(JsonObject)
RouterCallResult: TypeAlias = HarnessToolCallResult | Awaitable[HarnessToolCallResult]


class HarnessToolRouterProtocol(Protocol):
    def call(self, request: HarnessToolCallRequest) -> RouterCallResult: ...

    async def call_async(self, request: HarnessToolCallRequest) -> HarnessToolCallResult: ...


@dataclass(frozen=True, slots=True)
class FullHarnessMCPResourceNotFoundError(Exception):
    uri: str

    def __str__(self) -> str:
        return f"Full-harness MCP resource not found: {self.uri}"


class FullHarnessMCPResource(HarnessContract):
    uri: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mime_type: str = "application/json"


class FullHarnessMCPToolCallRequest(HarnessContract):
    tool_name: str = Field(min_length=1)
    arguments: JsonObject = Field(default_factory=dict)
    context: ToolContext
    source_mode: SourceMode = SourceMode.FIXTURE
    approval_id: str | None = None


class FullHarnessMCPAdapter:
    def __init__(self, router: HarnessToolRouterProtocol | None = None) -> None:
        self._router = router or default_tool_router()

    def list_tools(self) -> list[JsonObject]:
        return [_contract_json(tool) for tool in list_tool_specs()]

    async def call_tool_async(
        self, request: FullHarnessMCPToolCallRequest
    ) -> HarnessToolCallResult:
        router_request = _router_request(request)
        if hasattr(self._router, "call_async"):
            return await self._router.call_async(router_request)
        return await _resolve_router_result(self._router.call(router_request))

    def call_tool(self, request: FullHarnessMCPToolCallRequest) -> HarnessToolCallResult:
        router_request = _router_request(request)
        if hasattr(self._router, "call_async"):
            with anyio.from_thread.start_blocking_portal() as portal:
                return portal.call(self._router.call_async, router_request)
        router_result = self._router.call(router_request)
        if _is_router_result_awaitable(router_result):
            with anyio.from_thread.start_blocking_portal() as portal:
                return portal.call(_await_router_result, router_result)
        return cast(HarnessToolCallResult, router_result)

    def list_resources(self, run_id: RunId | None = None) -> list[FullHarnessMCPResource]:
        resources = [
            _resource("plotlot://harness/tools", "Harness Tools", "Full harness tool specs."),
            _resource("plotlot://harness/skills", "Harness Skills", "Full harness skill specs."),
            _resource("plotlot://source-catalog", "Source Catalog", "Combined fixture catalog."),
            _resource(
                "plotlot://source-catalog/south-florida-gis",
                "South Florida GIS",
                "Shared South Florida GIS source catalog.",
            ),
            _resource(
                "plotlot://source-catalog/municode",
                "Municode",
                "Fixture Municode ordinance source catalog.",
            ),
            _resource("plotlot://training/sources", "Training Sources", "Training video catalog."),
        ]
        if run_id is None:
            return resources
        return [
            *resources,
            _resource(f"plotlot://harness/runs/{run_id}/events", "Run Events", "Run events."),
            _resource(
                f"plotlot://harness/runs/{run_id}/evidence",
                "Run Evidence",
                "Evidence linked to a run.",
            ),
            _resource(
                f"plotlot://harness/runs/{run_id}/reports",
                "Run Reports",
                "Reports linked to a run.",
            ),
            _resource(
                f"plotlot://harness/runs/{run_id}/verification",
                "Run Verification",
                "Verification results linked to a run.",
            ),
        ]

    def read_resource(self, uri: str) -> JsonObject:
        match uri:
            case "plotlot://harness/tools":
                return _payload("tools", self.list_tools())
            case "plotlot://harness/skills":
                return _payload("skills", [_contract_json(skill) for skill in list_skill_specs()])
            case "plotlot://source-catalog":
                return _source_catalog()
            case "plotlot://source-catalog/south-florida-gis":
                return _gis_catalog()
            case "plotlot://source-catalog/municode":
                return _municode_catalog()
            case "plotlot://training/sources":
                return _training_sources()
        if run_id := _run_resource_id(uri, "/events"):
            return _run_events(run_id)
        if run_id := _run_resource_id(uri, "/evidence"):
            return _run_evidence(run_id)
        if run_id := _run_resource_id(uri, "/reports"):
            return _run_reports(run_id)
        if run_id := _run_resource_id(uri, "/verification"):
            return _run_verification(run_id)
        raise FullHarnessMCPResourceNotFoundError(uri=uri)


def _resource(uri: str, name: str, description: str) -> FullHarnessMCPResource:
    return FullHarnessMCPResource(uri=uri, name=name, description=description)


def _router_request(request: FullHarnessMCPToolCallRequest) -> HarnessToolCallRequest:
    return HarnessToolCallRequest(
        tool_name=request.tool_name,
        args=request.arguments,
        context=request.context,
        source_mode=request.source_mode,
        execution_mode=ExecutionMode.LOCAL,
        approval_id=request.approval_id,
    )


def _contract_json(contract: HarnessContract) -> JsonObject:
    return JSON_OBJECT_ADAPTER.validate_json(contract.model_dump_json())


def _payload(key: str, records: list[JsonObject]) -> JsonObject:
    return JSON_OBJECT_ADAPTER.validate_python(
        {"transport": "mcp", "source_mode": SourceMode.FIXTURE.value, key: records}
    )


def _source_catalog() -> JsonObject:
    return JSON_OBJECT_ADAPTER.validate_python(
        {
            "transport": "mcp",
            "source_mode": SourceMode.FIXTURE.value,
            "sources": [
                *[_contract_json(item) for item in load_south_florida_gis_source_catalog()],
                *[
                    _contract_json(item)
                    for item in load_municode_source_catalog(SourceMode.FIXTURE)
                ],
                *[
                    _contract_json(item)
                    for item in load_cost_assumption_source_catalog(SourceMode.FIXTURE)
                ],
            ],
        }
    )


def _gis_catalog() -> JsonObject:
    return _payload(
        "sources",
        [_contract_json(item) for item in load_south_florida_gis_source_catalog()],
    )


def _municode_catalog() -> JsonObject:
    return _payload(
        "sources",
        [_contract_json(item) for item in load_municode_source_catalog(SourceMode.FIXTURE)],
    )


def _training_sources() -> JsonObject:
    return _payload(
        "videos",
        [
            _contract_json(item)
            for item in discover_training_video_sources(source_mode=SourceMode.FIXTURE)
        ],
    )


def _run_resource_id(uri: str, suffix: str) -> RunId | None:
    prefix = "plotlot://harness/runs/"
    if not uri.startswith(prefix) or not uri.endswith(suffix):
        return None
    run_id = uri.removeprefix(prefix).removesuffix(suffix)
    if not run_id:
        return None
    return RunId(run_id)


def _run_events(run_id: RunId) -> JsonObject:
    return _payload(
        "events",
        [_contract_json(event) for event in default_harness_run_store().get_events(run_id)],
    )


def _run_evidence(run_id: RunId) -> JsonObject:
    return _payload(
        "evidence",
        [_contract_json(item) for item in default_evidence_ledger().list_evidence(run_id)],
    )


def _run_reports(run_id: RunId) -> JsonObject:
    return _payload(
        "reports",
        [_contract_json(item) for item in default_report_ledger().list_reports(run_id=run_id)],
    )


def _run_verification(run_id: RunId) -> JsonObject:
    return _payload(
        "verification",
        [
            _contract_json(item)
            for item in default_verification_ledger().list_verifications(run_id=run_id)
        ],
    )


def _is_router_result_awaitable(
    result: RouterCallResult,
) -> TypeGuard[Awaitable[HarnessToolCallResult]]:
    return inspect.isawaitable(result)


async def _resolve_router_result(result: RouterCallResult) -> HarnessToolCallResult:
    if _is_router_result_awaitable(result):
        return await _await_router_result(result)
    return cast(HarnessToolCallResult, result)


async def _await_router_result(result: Awaitable[HarnessToolCallResult]) -> HarnessToolCallResult:
    return await result
