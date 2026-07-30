from __future__ import annotations

from fastapi import APIRouter

from plotlot.harness.contracts import JsonObject
from plotlot.harness.health import collect_harness_health, filter_harness_health

router = APIRouter(prefix="/api/v1", tags=["harness-health"])


@router.get("/health")
async def api_v1_health() -> JsonObject:
    return collect_harness_health().model_dump(mode="json")


@router.get("/health/harness")
async def harness_health() -> JsonObject:
    return collect_harness_health().model_dump(mode="json")


@router.get("/health/sources")
async def source_health() -> JsonObject:
    return filter_harness_health(
        {"south_florida_gis_catalog", "municode_fixture_catalog", "training_fixture_catalog"}
    ).model_dump(mode="json")


@router.get("/health/providers")
async def provider_health() -> JsonObject:
    return filter_harness_health({"south_florida_gis_catalog", "codex_optional"}).model_dump(
        mode="json"
    )


@router.get("/health/queue")
async def queue_health() -> JsonObject:
    return filter_harness_health({"queue"}).model_dump(mode="json")


@router.get("/health/cli")
async def cli_health() -> JsonObject:
    return filter_harness_health({"cli"}).model_dump(mode="json")


@router.get("/health/training")
async def training_health() -> JsonObject:
    return filter_harness_health({"training_fixture_catalog"}).model_dump(mode="json")
