from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.analysis_run_link import (
    HarnessAnalysisContextError,
    persist_analysis_run_link,
    validate_harness_analysis_context,
)
from plotlot.harness.contracts import (
    CountyName,
    ExecutionMode,
    JsonObject,
    PlotLotEventType,
    RunId,
    SourceMode,
)
from plotlot.harness.debug_bundle import default_debug_bundle_stores, export_debug_bundle
from plotlot.harness.cost_assumption_source import load_cost_assumption_source_catalog
from plotlot.harness.fixture_runs import (
    FixtureDealRunRequest,
    run_deal_analysis_async,
)
from plotlot.harness.full_harness_registry import (
    list_agent_role_specs,
    list_skill_specs,
    list_tool_specs,
)
from plotlot.harness.municode_source import load_municode_source_catalog
from plotlot.harness.run_persistence import (
    default_fixture_run_persistence_stores,
    persist_fixture_run_result,
)
from plotlot.harness.run_store import (
    HarnessRunCancellationRequest,
    HarnessRunNotFoundError,
    RunCancellationBlockedError,
    default_harness_run_store,
)
from plotlot.harness.south_florida_gis import (
    load_south_florida_gis_source_catalog,
    search_south_florida_gis,
)
from plotlot.harness.training_ingestion import (
    build_training_knowledge_index,
    discover_training_video_sources,
    extract_training_concepts,
    normalize_transcript,
    search_training_knowledge,
    segment_transcript,
)
from plotlot.storage.db import get_session

router = APIRouter(prefix="/api/v1", tags=["harness"])


class GISSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1)
    county: str | None = None
    source_mode: SourceMode = SourceMode.FIXTURE


class TrainingDiscoverRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str | None = None
    category: str | None = None
    source_mode: SourceMode = SourceMode.FIXTURE


class TrainingSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    keyword: str | None = None
    calculator: str | None = None
    source_mode: SourceMode = SourceMode.FIXTURE


class DealAnalysisRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    address: str = Field(min_length=3)
    analysis_type: str = Field(
        default="acquisition_memo",
        min_length=1,
        validation_alias="analysisType",
    )
    source_mode: SourceMode = Field(
        default=SourceMode.FIXTURE,
        validation_alias="sourceMode",
    )
    assumptions: JsonObject = Field(default_factory=dict)
    workspace_id: str | None = Field(default=None, validation_alias="workspaceId")
    project_id: str | None = Field(default=None, validation_alias="projectId")
    site_id: str | None = Field(default=None, validation_alias="siteId")
    analysis_id: str | None = Field(default=None, validation_alias="analysisId")


class RunCancellationRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = Field(default="Cancellation requested.", min_length=1)
    actor_user_id: str = Field(default="api", min_length=1)


def _require_fixture_source_mode(source_mode: SourceMode) -> None:
    if source_mode is not SourceMode.FIXTURE:
        raise HTTPException(
            status_code=501,
            detail="Only fixture source mode is wired in this harness slice",
        )


@router.get("/harness/skills")
async def harness_skills() -> JsonObject:
    return {"skills": [skill.model_dump(mode="json") for skill in list_skill_specs()]}


@router.get("/harness/roles")
async def harness_roles() -> JsonObject:
    return {"roles": [role.model_dump(mode="json") for role in list_agent_role_specs()]}


@router.get("/harness/registry")
async def harness_registry() -> JsonObject:
    skills = list_skill_specs()
    tools = list_tool_specs()
    roles = list_agent_role_specs()
    return {
        "skills": [skill.model_dump(mode="json") for skill in skills],
        "tools": [tool.model_dump(mode="json") for tool in tools],
        "roles": [role.model_dump(mode="json") for role in roles],
        "counts": {
            "skills": len(skills),
            "tools": len(tools),
            "roles": len(roles),
        },
    }


@router.get("/harness/events/schema")
async def harness_events_schema() -> JsonObject:
    return {"event_types": [event_type.value for event_type in PlotLotEventType]}


@router.get("/source-catalog")
async def source_catalog(source_mode: SourceMode = SourceMode.FIXTURE) -> JsonObject:
    _require_fixture_source_mode(source_mode)
    sources = load_south_florida_gis_source_catalog(source_mode)
    sources.extend(load_municode_source_catalog(source_mode))
    sources.extend(load_cost_assumption_source_catalog(source_mode))
    return {
        "source_mode": source_mode.value,
        "sources": [item.model_dump(mode="json") for item in sources],
    }


@router.post("/gis/search")
async def gis_search(body: GISSearchRequest) -> JsonObject:
    _require_fixture_source_mode(body.source_mode)
    county = CountyName(body.county) if body.county else None
    results = search_south_florida_gis(body.query, county=county, source_mode=body.source_mode)
    return {
        "source_mode": body.source_mode.value,
        "results": [item.model_dump(mode="json") for item in results],
    }


@router.get("/gis/sources/{source_id}")
async def gis_source(source_id: str, source_mode: SourceMode = SourceMode.FIXTURE) -> JsonObject:
    _require_fixture_source_mode(source_mode)
    for item in load_south_florida_gis_source_catalog(source_mode):
        if item.source_id == source_id:
            return item.model_dump(mode="json")
    raise HTTPException(status_code=404, detail="GIS source not found")


@router.post("/training/discover")
async def training_discover(body: TrainingDiscoverRequest) -> JsonObject:
    _require_fixture_source_mode(body.source_mode)
    videos = discover_training_video_sources(
        source_mode=body.source_mode,
        url=body.url,
        category=body.category,
    )
    return {
        "source_mode": body.source_mode.value,
        "videos": [video.model_dump(mode="json") for video in videos],
    }


@router.post("/training/search")
async def training_search(body: TrainingSearchRequest) -> JsonObject:
    _require_fixture_source_mode(body.source_mode)
    videos = discover_training_video_sources(source_mode=body.source_mode)
    concepts = []
    for video in videos:
        if video.access_status.value == "public":
            transcript = normalize_transcript(video)
            concepts.extend(extract_training_concepts(transcript, segment_transcript(transcript)))
    knowledge = build_training_knowledge_index(concepts)
    results = search_training_knowledge(knowledge, keyword=body.keyword, calculator=body.calculator)
    return {
        "source_mode": body.source_mode.value,
        "results": [item.model_dump(mode="json") for item in results],
    }


@router.post("/deal-analysis/run")
async def deal_analysis_run(body: DealAnalysisRunRequest) -> JsonObject:
    request = FixtureDealRunRequest(
        address=body.address,
        analysis_type=body.analysis_type,
        source_mode=body.source_mode,
        assumptions=body.assumptions,
        workspace_id=body.workspace_id,
        project_id=body.project_id,
        site_id=body.site_id,
        analysis_id=body.analysis_id,
    )
    session = await get_session()
    try:
        try:
            context = await validate_harness_analysis_context(session, request)
        except HarnessAnalysisContextError as exc:
            status_code = 400 if "both required" in str(exc) else 404
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        result = await run_deal_analysis_async(request)
        result = await persist_analysis_run_link(
            session,
            context=context,
            request=request,
            result=result,
        )
        persist_fixture_run_result(
            result,
            default_fixture_run_persistence_stores(),
        )
        return result.model_dump(mode="json")
    finally:
        await session.close()


@router.get("/harness/runs/{run_id}")
async def harness_run(run_id: str) -> JsonObject:
    try:
        result = default_harness_run_store().get_run(RunId(run_id))
    except HarnessRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.get("/harness/runs/{run_id}/events")
async def harness_run_events(run_id: str) -> JsonObject:
    try:
        events = default_harness_run_store().get_events(RunId(run_id))
    except HarnessRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run_id, "events": [event.model_dump(mode="json") for event in events]}


@router.post("/harness/runs/{run_id}/replay")
async def harness_run_replay(run_id: str) -> JsonObject:
    try:
        replay = default_harness_run_store().replay_run(RunId(run_id))
    except HarnessRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return replay.model_dump(mode="json")


@router.post("/harness/runs/{run_id}/cancel")
async def harness_run_cancel(
    run_id: str,
    body: RunCancellationRequestBody | None = None,
) -> JsonObject:
    request_body = body or RunCancellationRequestBody()
    try:
        result = default_harness_run_store().cancel_run(
            HarnessRunCancellationRequest(
                run_id=RunId(run_id),
                actor_user_id=request_body.actor_user_id,
                reason=request_body.reason,
                execution_mode=ExecutionMode.API,
            )
        )
    except HarnessRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunCancellationBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "run_cancellation_blocked",
                "reason": exc.reason,
                "current_status": exc.current_status,
            },
        ) from exc
    return result.model_dump(mode="json")


@router.get("/harness/runs/{run_id}/debug-bundle")
async def harness_run_debug_bundle(run_id: str) -> JsonObject:
    try:
        bundle = export_debug_bundle(RunId(run_id), default_debug_bundle_stores())
    except HarnessRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return bundle.model_dump(mode="json")
