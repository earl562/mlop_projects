"""Ordinance Intelligence API — structured access to Municode zoning data.

Wraps the existing ingestion, search, and discovery layers as queryable
internal endpoints. No new DB tables — reads OrdinanceChunk and
IngestionCheckpoint exclusively.

Endpoints:
  GET  /api/v1/ordinance/municipalities           — list all discoverable municipalities
  GET  /api/v1/ordinance/municipalities/{key}     — single municipality detail + config
  POST /api/v1/ordinance/search                   — hybrid ordinance search (rate-limited)
  GET  /api/v1/ordinance/section/{node_id}        — fetch raw Municode section content
  GET  /api/v1/ordinance/coverage                 — data freshness per municipality
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from plotlot.ingestion.discovery import get_all_municode_configs
from plotlot.ingestion.embedder import embed_texts
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session
from plotlot.storage.models import IngestionCheckpoint, OrdinanceChunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ordinance", tags=["ordinance"])

# node_id values from Municode are uppercase alphanumeric with underscores,
# hyphens, and dots (e.g. "PTIIICOOR_CH33ZO", "ARTIIZODIRE-1.2").
# Reject anything else before passing to external APIs.
_NODE_ID_RE = re.compile(r"^[A-Z0-9_\-.]{1,200}$")


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------


class MunicipalityListItem(BaseModel):
    key: str
    name: str
    county: str
    state: str
    ingested: bool
    chunk_count: int


class MunicipalityListResponse(BaseModel):
    total: int
    ingested_count: int
    municipalities: list[MunicipalityListItem]


class MunicipalityDetailResponse(BaseModel):
    key: str
    name: str
    county: str
    state: str
    client_id: int
    product_id: int
    job_id: int
    zoning_node_id: str
    ingested: bool
    chunk_count: int
    last_ingested_at: datetime | None
    data_age_days: int | None


class OrdinanceSearchRequest(BaseModel):
    municipality: str = Field(..., min_length=2, max_length=200)
    query: str = Field(..., min_length=3, max_length=500)
    zone_code: str = Field(default="", max_length=50)
    limit: int = Field(default=10, ge=1, le=25)


class OrdinanceSearchResult(BaseModel):
    section: str
    section_title: str
    zone_codes: list[str]
    chunk_text: str
    score: float


class OrdinanceSearchResponse(BaseModel):
    municipality: str
    query: str
    result_count: int
    results: list[OrdinanceSearchResult]


class SectionResponse(BaseModel):
    node_id: str
    municipality_key: str
    text: str
    html: str


class CoverageItem(BaseModel):
    municipality: str
    county: str
    state: str
    chunk_count: int
    last_ingested_at: datetime | None
    data_age_days: int | None
    embedding_model: str | None


class CoverageResponse(BaseModel):
    total_chunks: int
    municipality_count: int
    municipalities: list[CoverageItem]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_chunk_counts() -> dict[str, int]:
    """Return {municipality_name_lower: chunk_count} from the DB."""
    session = await get_session()
    try:
        result = await session.execute(
            select(
                OrdinanceChunk.municipality,
                func.count().label("chunks"),
            ).group_by(OrdinanceChunk.municipality)
        )
        return {row.municipality.lower(): row.chunks for row in result.fetchall()}
    finally:
        await session.close()


async def _get_latest_checkpoints() -> dict[str, IngestionCheckpoint]:
    """Return {municipality_key: latest completed IngestionCheckpoint} from the DB."""
    session = await get_session()
    try:
        # Subquery: latest completed_at per municipality_key
        subq = (
            select(
                IngestionCheckpoint.municipality_key,
                func.max(IngestionCheckpoint.completed_at).label("latest"),
            )
            .where(IngestionCheckpoint.status == "complete")
            .group_by(IngestionCheckpoint.municipality_key)
            .subquery()
        )
        result = await session.execute(
            select(IngestionCheckpoint).join(
                subq,
                (IngestionCheckpoint.municipality_key == subq.c.municipality_key)
                & (IngestionCheckpoint.completed_at == subq.c.latest),
            )
        )
        rows = result.scalars().all()
        return {row.municipality_key: row for row in rows}
    finally:
        await session.close()


def _data_age_days(completed_at: datetime | None) -> int | None:
    if completed_at is None:
        return None
    now = datetime.now(timezone.utc)
    aware = (
        completed_at.replace(tzinfo=timezone.utc) if completed_at.tzinfo is None else completed_at
    )
    return (now - aware).days


# ---------------------------------------------------------------------------
# GET /municipalities
# ---------------------------------------------------------------------------


@router.get("/municipalities", response_model=MunicipalityListResponse)
async def list_municipalities() -> MunicipalityListResponse:
    """List all discoverable municipalities across FL, NC, TX, GA, SC.

    Merges the live Municode discovery cache with DB chunk counts to show
    which municipalities have been ingested and how many chunks each has.
    Results are served from the in-memory / disk cache — no Municode API
    call is made on warm servers.
    """
    configs, chunk_counts = await asyncio.gather(
        get_all_municode_configs(),
        _get_chunk_counts(),
    )

    items: list[MunicipalityListItem] = []
    for key, config in sorted(configs.items()):
        count = chunk_counts.get(config.municipality.lower(), 0)
        items.append(
            MunicipalityListItem(
                key=key,
                name=config.municipality,
                county=config.county,
                state=config.state,
                ingested=count > 0,
                chunk_count=count,
            )
        )

    ingested_count = sum(1 for item in items if item.ingested)
    return MunicipalityListResponse(
        total=len(items),
        ingested_count=ingested_count,
        municipalities=items,
    )


# ---------------------------------------------------------------------------
# GET /municipalities/{key}
# ---------------------------------------------------------------------------


@router.get("/municipalities/{key}", response_model=MunicipalityDetailResponse)
async def get_municipality(key: str) -> MunicipalityDetailResponse:
    """Return full config and ingestion detail for a single municipality.

    `key` is the snake_case municipality key, e.g. ``miami_gardens``.
    Returns 404 if the key is not in the discovery catalog.
    """
    configs = await get_all_municode_configs()
    config = configs.get(key)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Municipality '{key}' not found. "
            "Call GET /api/v1/ordinance/municipalities to see available keys.",
        )

    chunk_counts, checkpoints = await asyncio.gather(
        _get_chunk_counts(),
        _get_latest_checkpoints(),
    )

    chunk_count = chunk_counts.get(config.municipality.lower(), 0)
    checkpoint = checkpoints.get(key)
    last_ingested_at = checkpoint.completed_at if checkpoint else None

    return MunicipalityDetailResponse(
        key=key,
        name=config.municipality,
        county=config.county,
        state=config.state,
        client_id=config.client_id,
        product_id=config.product_id,
        job_id=config.job_id,
        zoning_node_id=config.zoning_node_id,
        ingested=chunk_count > 0,
        chunk_count=chunk_count,
        last_ingested_at=last_ingested_at,
        data_age_days=_data_age_days(last_ingested_at),
    )


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post("/search", response_model=OrdinanceSearchResponse)
async def search_ordinances(
    body: OrdinanceSearchRequest,
    request: Request,
) -> OrdinanceSearchResponse:
    """Hybrid ordinance search — vector similarity + BM25 with RRF fusion.

    Directly exposes the same search layer the analysis pipeline uses internally.
    One NVIDIA NIM embedding call per request (input_type="query").

    Rate-limited in line with /analyze — prevents embedding API abuse.
    """
    from plotlot.api.middleware import rate_limiter

    await rate_limiter.check(request)

    # Embed the natural-language query for vector similarity
    try:
        embeddings = await embed_texts([body.query], input_type="query")
        query_embedding = embeddings[0]
    except Exception as exc:
        logger.error("Embedding failed for ordinance search: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable — please try again shortly.",
        )

    # Run hybrid search (RRF fusion: vector + BM25)
    # zone_code drives keyword matching; query embedding drives vector matching
    session = await get_session()
    try:
        results = await hybrid_search(
            session=session,
            municipality=body.municipality,
            zone_code=body.zone_code or body.query,
            limit=body.limit,
            embedding=query_embedding,
        )
    except Exception as exc:
        logger.error(
            "Ordinance search failed for %s / %r: %s",
            body.municipality,
            body.query,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Search service unavailable — please try again shortly.",
        )
    finally:
        await session.close()

    return OrdinanceSearchResponse(
        municipality=body.municipality,
        query=body.query,
        result_count=len(results),
        results=[
            OrdinanceSearchResult(
                section=r.section,
                section_title=r.section_title,
                zone_codes=r.zone_codes,
                chunk_text=r.chunk_text,
                score=round(r.score, 4),
            )
            for r in results
        ],
    )


# ---------------------------------------------------------------------------
# GET /section/{node_id}
# ---------------------------------------------------------------------------


@router.get("/section/{node_id}", response_model=SectionResponse)
async def get_section(
    node_id: str,
    municipality_key: str = Query(
        ...,
        description="Snake-case municipality key, e.g. 'miami_gardens'. "
        "Required because node IDs are municipality-scoped on Municode.",
    ),
) -> SectionResponse:
    """Fetch the raw content of a specific Municode ordinance section.

    Uses the ``municode_node_id`` stored on every chunk to retrieve the
    original ordinance text directly from Municode's API. Returns both the
    raw HTML and the plain-text version for rendering flexibility.

    Returns 400 if the node_id contains invalid characters.
    Returns 404 if the municipality_key is not in the discovery catalog.
    Returns 503 if the Municode API times out or returns an error.
    """
    # Validate node_id — never forward unvalidated user input to an external URL
    if not _NODE_ID_RE.match(node_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid node_id format. "
                "Municode node IDs contain only uppercase letters, digits, "
                "underscores, hyphens, and dots."
            ),
        )

    configs = await get_all_municode_configs()
    config = configs.get(municipality_key)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Municipality key '{municipality_key}' not found. "
            "Call GET /api/v1/ordinance/municipalities to see available keys.",
        )

    scraper = MunicodeScraper(max_concurrent=1)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            html = await asyncio.wait_for(
                scraper.get_section_content(client, config, node_id),
                timeout=10.0,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Municode section fetch timed out: node_id=%s municipality=%s",
            node_id,
            municipality_key,
        )
        raise HTTPException(
            status_code=503,
            detail="Municode API did not respond in time — please try again.",
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Municode API returned %d for node_id=%s",
            exc.response.status_code,
            node_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Municode API returned HTTP {exc.response.status_code}.",
        )
    except Exception as exc:
        logger.error("Municode section fetch failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve section from Municode — please try again.",
        )

    text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)

    return SectionResponse(
        node_id=node_id,
        municipality_key=municipality_key,
        text=text,
        html=html,
    )


# ---------------------------------------------------------------------------
# GET /coverage
# ---------------------------------------------------------------------------


@router.get("/coverage", response_model=CoverageResponse)
async def get_coverage() -> CoverageResponse:
    """Data freshness report for all ingested municipalities.

    Shows chunk counts, last ingestion timestamp, and data age in days.
    Sourced entirely from the DB — no external API calls.
    """
    session = await get_session()
    try:
        # Chunk counts + embedding model per municipality
        chunk_result = await session.execute(
            select(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
                func.count().label("chunk_count"),
                func.max(OrdinanceChunk.embedding_model).label("embedding_model"),
            )
            .group_by(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
            )
            .order_by(func.count().desc())
        )
        chunk_rows = chunk_result.fetchall()

        # Latest completed checkpoint per municipality_key
        subq = (
            select(
                IngestionCheckpoint.municipality_key,
                func.max(IngestionCheckpoint.completed_at).label("latest"),
            )
            .where(IngestionCheckpoint.status == "complete")
            .group_by(IngestionCheckpoint.municipality_key)
            .subquery()
        )
        checkpoint_result = await session.execute(
            select(IngestionCheckpoint).join(
                subq,
                (IngestionCheckpoint.municipality_key == subq.c.municipality_key)
                & (IngestionCheckpoint.completed_at == subq.c.latest),
            )
        )
        checkpoints = {row.municipality_key: row for row in checkpoint_result.scalars().all()}
    finally:
        await session.close()

    # Build a name→key reverse map so we can look up checkpoints by municipality name
    try:
        configs = await get_all_municode_configs()
        name_to_key = {cfg.municipality.lower(): key for key, cfg in configs.items()}
    except Exception:
        name_to_key = {}

    items: list[CoverageItem] = []
    total_chunks = 0

    for row in chunk_rows:
        total_chunks += row.chunk_count
        muni_key = name_to_key.get(row.municipality.lower())
        checkpoint = checkpoints.get(muni_key) if muni_key else None
        last_ingested_at = checkpoint.completed_at if checkpoint else None

        items.append(
            CoverageItem(
                municipality=row.municipality,
                county=row.county,
                state=row.state or "FL",
                chunk_count=row.chunk_count,
                last_ingested_at=last_ingested_at,
                data_age_days=_data_age_days(last_ingested_at),
                embedding_model=row.embedding_model,
            )
        )

    return CoverageResponse(
        total_chunks=total_chunks,
        municipality_count=len(items),
        municipalities=items,
    )
