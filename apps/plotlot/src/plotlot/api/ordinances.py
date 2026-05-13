"""Ordinance Intelligence API.

This API makes the existing pgvector/Municode retrieval layer agent-native
without exposing raw Municode browsing as the internal product contract.
"""

from __future__ import annotations

import re
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.evidence import EvidenceService
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session
from plotlot.storage.models import OrdinanceChunk

router = APIRouter(prefix="/api/v1", tags=["ordinances"])


class OrdinanceSearchRequest(BaseModel):
    jurisdiction: str | None = None
    municipality: str | None = None
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class OrdinanceSearchHit(BaseModel):
    section_id: str
    section: str
    title: str
    text_preview: str
    municipality: str
    score: float
    source_url: str | None = None


class OrdinanceSearchResponse(BaseModel):
    results: list[OrdinanceSearchHit]


class OrdinanceSectionResponse(BaseModel):
    section_id: str
    section: str | None = None
    title: str | None = None
    municipality: str
    county: str | None = None
    body: str
    source_url: str | None = None
    retrieved_at: str | None = None


class ExtractRulesRequest(BaseModel):
    jurisdiction: str | None = None
    municipality: str | None = None
    zoning_code: str
    sections: list[str] = Field(default_factory=list)
    text: str | None = None
    rule_types: list[str] = Field(default_factory=list)


class ExtractedRule(BaseModel):
    rule_type: str
    value: str | float
    unit: str | None = None
    raw_text: str
    source_section: str | None = None
    confidence: str = "medium"


class ExtractRulesResponse(BaseModel):
    zoning_code: str
    rules: list[ExtractedRule]
    open_questions: list[str] = Field(default_factory=list)


class ValidateClaimRequest(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)


class ValidateClaimResponse(BaseModel):
    supported: bool
    confidence: str
    supporting_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _jurisdiction_to_municipality(payload: OrdinanceSearchRequest | ExtractRulesRequest) -> str:
    value = payload.municipality or payload.jurisdiction
    if not value:
        raise HTTPException(status_code=422, detail="municipality or jurisdiction is required")
    return value.replace("_", " ")


def _preview(text: str, limit: int = 320) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _rule_type_from_context(prefix: str, sentence: str) -> str:
    lowered = f"{prefix} {sentence}".lower()
    if "front" in lowered:
        return "front_setback"
    if "side" in lowered:
        return "side_setback"
    if "rear" in lowered:
        return "rear_setback"
    if "height" in lowered:
        return "max_height"
    if "coverage" in lowered:
        return "lot_coverage"
    if "far" in lowered or "floor area" in lowered:
        return "floor_area_ratio"
    if "lot" in lowered and ("area" in lowered or "size" in lowered):
        return "min_lot_size"
    return "dimensional_standard"


def _extract_simple_rules(
    text: str,
    source_section: str | None,
    rule_types: list[str],
) -> list[ExtractedRule]:
    """Small deterministic extractor for common dimensional standards.

    This is deliberately conservative. Full legal interpretation remains a
    skill/runtime concern; this endpoint provides structured candidates with
    source snippets and confidence.
    """

    rules: list[ExtractedRule] = []
    sentences = re.split(r"(?<=[.;:])\s+", text)
    numeric_pattern = (
        r"(?P<prefix>.{0,80}?)(?P<value>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>feet|foot|ft\.?|percent|%|stories|story|sq\.?\s*ft\.?|square feet|acres?)"
    )
    far_pattern = (
        r"(?P<prefix>.{0,80}?)(?P<value>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>FAR|floor area ratio)"
    )
    patterns = [(numeric_pattern, "numeric_standard"), (far_pattern, "floor_area_ratio")]

    allowed = {rule.lower() for rule in rule_types}
    for sentence in sentences:
        for pattern, fallback_type in patterns:
            for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
                rule_type = _rule_type_from_context(match.group("prefix"), sentence)
                if rule_type == "dimensional_standard":
                    rule_type = fallback_type
                if allowed and rule_type not in allowed:
                    continue
                value = match.group("value")
                unit = match.group("unit").replace(".", "").lower()
                parsed_value: str | float
                try:
                    parsed_value = float(value)
                except ValueError:
                    parsed_value = value
                rules.append(
                    ExtractedRule(
                        rule_type=rule_type,
                        value=parsed_value,
                        unit=unit,
                        raw_text=_preview(sentence, limit=420),
                        source_section=source_section,
                        confidence="medium",
                    )
                )
                if len(rules) >= 24:
                    return rules
    return rules


async def _load_section(session: AsyncSession, section_id: str) -> OrdinanceChunk | None:
    stmt = select(OrdinanceChunk)
    if section_id.isdigit():
        stmt = stmt.where(OrdinanceChunk.id == int(section_id))
    else:
        stmt = stmt.where(
            or_(
                OrdinanceChunk.section == section_id,
                OrdinanceChunk.municode_node_id == section_id,
            )
        )
    result = await session.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def search_ordinance_records(
    session: AsyncSession,
    *,
    municipality: str,
    query: str,
    limit: int,
) -> list[OrdinanceSearchHit]:
    results = await hybrid_search(session, municipality, query, limit=limit)
    return [
        OrdinanceSearchHit(
            section_id=result.section or f"{result.municipality}:{index}",
            section=result.section,
            title=result.section_title,
            text_preview=_preview(result.chunk_text),
            municipality=result.municipality,
            score=result.score,
        )
        for index, result in enumerate(results)
    ]


@router.post("/ordinances/search", response_model=OrdinanceSearchResponse)
async def search_ordinances(
    payload: OrdinanceSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> OrdinanceSearchResponse:
    municipality = _jurisdiction_to_municipality(payload)
    return OrdinanceSearchResponse(
        results=await search_ordinance_records(
            session,
            municipality=municipality,
            query=payload.query,
            limit=payload.limit,
        )
    )


@router.get("/ordinances/sections/{section_id}", response_model=OrdinanceSectionResponse)
async def get_ordinance_section(
    section_id: str,
    session: AsyncSession = Depends(get_session),
) -> OrdinanceSectionResponse:
    chunk = await _load_section(session, section_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Ordinance section not found")
    return OrdinanceSectionResponse(
        section_id=str(chunk.id),
        section=cast(str | None, chunk.section),
        title=cast(str | None, chunk.section_title),
        municipality=cast(str, chunk.municipality),
        county=cast(str | None, chunk.county),
        body=cast(str, chunk.chunk_text),
        source_url=cast(str | None, chunk.source_url),
        retrieved_at=chunk.scraped_at.isoformat() if chunk.scraped_at else None,
    )


@router.post("/ordinances/extract-rules", response_model=ExtractRulesResponse)
async def extract_rules(
    payload: ExtractRulesRequest,
    session: AsyncSession = Depends(get_session),
) -> ExtractRulesResponse:
    texts: list[tuple[str | None, str]] = []
    if payload.text:
        texts.append((None, payload.text))
    for section_id in payload.sections:
        chunk = await _load_section(session, section_id)
        if chunk is not None:
            texts.append((cast(str | None, chunk.section), cast(str, chunk.chunk_text)))

    if not texts:
        municipality = _jurisdiction_to_municipality(payload)
        hits = await search_ordinance_records(
            session,
            municipality=municipality,
            query=f"{payload.zoning_code} setbacks height lot size density",
            limit=5,
        )
        texts.extend((hit.section, hit.text_preview) for hit in hits)

    rules: list[ExtractedRule] = []
    for source_section, text in texts:
        rules.extend(_extract_simple_rules(text, source_section, payload.rule_types))

    return ExtractRulesResponse(
        zoning_code=payload.zoning_code,
        rules=rules,
        open_questions=[]
        if rules
        else ["No dimensional standards were extracted from the supplied sections."],
    )


@router.get("/zoning-rules", response_model=ExtractRulesResponse)
async def get_zoning_rules(
    jurisdiction: str | None = None,
    municipality: str | None = None,
    zoning_code: str = "",
    session: AsyncSession = Depends(get_session),
) -> ExtractRulesResponse:
    if not zoning_code:
        raise HTTPException(status_code=422, detail="zoning_code is required")
    payload = ExtractRulesRequest(
        jurisdiction=jurisdiction,
        municipality=municipality,
        zoning_code=zoning_code,
    )
    return await extract_rules(payload, session)


@router.post("/evidence/validate-claim", response_model=ValidateClaimResponse)
async def validate_claim(
    payload: ValidateClaimRequest,
    session: AsyncSession = Depends(get_session),
) -> ValidateClaimResponse:
    items = await EvidenceService(session).get_many(payload.evidence_ids)
    if not items:
        return ValidateClaimResponse(
            supported=False,
            confidence="low",
            warnings=["No evidence records were provided."],
        )

    claim_tokens = {
        token for token in re.findall(r"[a-z0-9]+", payload.claim.lower()) if len(token) > 2
    }
    supporting: list[str] = []
    for item in items:
        haystack = " ".join(
            [
                cast(str, item.claim_key) or "",
                str(cast(object, item.value_json) or ""),
                cast(str | None, item.source_title) or "",
                cast(str | None, item.source_url) or "",
            ]
        ).lower()
        if any(token in haystack for token in claim_tokens):
            supporting.append(cast(str, item.id))

    return ValidateClaimResponse(
        supported=bool(supporting),
        confidence="medium" if supporting else "low",
        supporting_sources=supporting,
        warnings=[] if supporting else ["Claim was not matched to the supplied evidence records."],
    )
