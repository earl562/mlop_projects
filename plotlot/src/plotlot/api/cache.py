"""Report-level cache backed by PostgreSQL.

Avoids redundant LLM pipeline runs for repeated queries on the same address.
Reports are cached with a configurable TTL (default 24h) and a hit counter
for observability dashboards.

Production relevance: at Stripe-scale, prompt caching + response caching
reduced LLM costs by 86% (Care Access case study). Even at PlotLot's scale,
caching a single address saves ~$0.001 per repeat query and eliminates
a 30-60s pipeline latency.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import select, update

from plotlot.storage.db import get_session
from plotlot.storage.models import ReportCache
from plotlot.security.context import current_tenant_id

CACHE_TTL_HOURS = 24


def normalize_address(address: str) -> str:
    """Normalize address for cache key.

    Strips whitespace, lowercases, removes punctuation that varies across
    user inputs (commas, periods), and collapses double spaces. This ensures
    "123 Main St, Miami, FL" and "123 main st  miami  fl" hit the same cache.
    """
    return address.strip().lower().replace(",", "").replace(".", "").replace("  ", " ")


async def get_cached_report(address: str, analysis_type: str = "residential") -> dict | None:
    """Check cache for a valid (non-expired) report.

    Returns the cached report_json dict if found, or None. Increments
    hit_count on cache hit for observability.
    """
    normalized = normalize_address(address)
    workspace_id = current_tenant_id()
    session = await get_session()
    try:
        result = await session.execute(
            select(ReportCache).where(
                ReportCache.workspace_id == workspace_id,
                ReportCache.address_normalized == normalized,
                ReportCache.analysis_type == analysis_type,
                ReportCache.expires_at > datetime.now(timezone.utc),
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            await session.execute(
                update(ReportCache)
                .where(ReportCache.id == cached.id)
                .values(hit_count=ReportCache.hit_count + 1)
            )
            await session.commit()
            report_data: dict[str, Any] = cast(dict, cached.report_json)  # type: ignore[assignment]
            return report_data
        return None
    finally:
        await session.close()


def _should_cache(report: dict) -> bool:
    """Quality gate — don't cache bad results.

    Skip caching when the report has low confidence, missing zoning district,
    or missing numeric params. Prevents polluting the cache with unreliable data.
    """
    if report.get("confidence") == "low":
        return False
    if not report.get("zoning_district"):
        return False
    if report.get("numeric_params") is None:
        return False
    return True


async def cache_report(address: str, report: dict, analysis_type: str = "residential") -> None:
    """Store a report in cache with TTL.

    Uses upsert semantics: if the (address, analysis_type) key already exists,
    the report is replaced and the TTL is reset.

    Quality gate: skips caching low-confidence or incomplete reports.
    """
    if not _should_cache(report):
        import logging

        logging.getLogger(__name__).info(
            "Skipping cache for %s/%s (quality gate: confidence=%s, district=%s, params=%s)",
            address[:40],
            analysis_type,
            report.get("confidence"),
            bool(report.get("zoning_district")),
            report.get("numeric_params") is not None,
        )
        return

    normalized = normalize_address(address)
    workspace_id = current_tenant_id()
    session = await get_session()
    try:
        existing = await session.execute(
            select(ReportCache).where(
                ReportCache.workspace_id == workspace_id,
                ReportCache.address_normalized == normalized,
                ReportCache.analysis_type == analysis_type,
            )
        )
        cached = existing.scalar_one_or_none()
        if cached:
            cached.report_json = report  # type: ignore[assignment]
            cached.expires_at = datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS)  # type: ignore[assignment]
            cached.hit_count = 0  # type: ignore[assignment]
        else:
            session.add(
                ReportCache(
                    workspace_id=workspace_id,
                    address=address,
                    address_normalized=normalized,
                    analysis_type=analysis_type,
                    report_json=report,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS),
                )
            )
        await session.commit()
    finally:
        await session.close()
