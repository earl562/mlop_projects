from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.contracts import JsonObject, SourceMode
from plotlot.harness.municode_source import (
    MunicodeModeUnsupportedError,
    MunicodeSectionNotFoundError,
    extract_ordinance_rules,
    get_municode_section,
    search_municode,
)

router = APIRouter(prefix="/api/v1", tags=["harness-municode"])


class MunicodeSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    jurisdiction: str = Field(min_length=1)
    query: str = Field(min_length=1)
    source_mode: SourceMode = SourceMode.FIXTURE


class OrdinanceRuleExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    section_id: str = Field(min_length=1)
    source_mode: SourceMode = SourceMode.FIXTURE


@router.post("/municode/search")
async def municode_search(body: MunicodeSearchRequest) -> JsonObject:
    try:
        results = search_municode(
            jurisdiction=body.jurisdiction,
            query=body.query,
            source_mode=body.source_mode,
        )
    except MunicodeModeUnsupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return {
        "source_mode": body.source_mode.value,
        "results": [item.model_dump(mode="json") for item in results],
    }


@router.get("/municode/sections/{section_id}")
async def municode_section(
    section_id: str, source_mode: SourceMode = SourceMode.FIXTURE
) -> JsonObject:
    try:
        section = get_municode_section(section_id, source_mode=source_mode)
    except MunicodeSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MunicodeModeUnsupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return section.model_dump(mode="json")


@router.post("/ordinances/extract-rules")
async def ordinance_extract_rules(body: OrdinanceRuleExtractionRequest) -> JsonObject:
    try:
        section = get_municode_section(body.section_id, source_mode=body.source_mode)
    except MunicodeSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MunicodeModeUnsupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return extract_ordinance_rules(section).model_dump(mode="json")
