"""Batch "buy box" screening — turn PlotLot into a deal-sourcing engine.

A developer defines a buy box (markets, zoning, lot size, min units, min
residual, …) and screens many candidate addresses at once. Each address runs
through the analysis pipeline; the residual max land offer ranks the survivors
so the best deals float to the top.

Layering:
  * ``evaluate_buy_box`` / ``_assemble`` — pure, deterministic filtering + ranking.
  * ``screen_reports`` — screen already-analyzed reports (pure).
  * ``screen_addresses`` — async orchestration with bounded concurrency,
    per-item timeout + error isolation, and an optional streaming callback.

The analysis function is injected (default wired in the API layer) so the core
is unit-testable without network, LLM, or DB access.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from plotlot.core.types import ZoningReport

logger = logging.getLogger(__name__)

AnalyzeFn = Callable[[str], Awaitable[ZoningReport | None]]


@dataclass
class BuyBox:
    """Acquisition criteria a deal must satisfy to qualify."""

    states: list[str] = field(default_factory=list)  # e.g. ["CA", "FL"]
    counties: list[str] = field(default_factory=list)  # matched case-insensitively
    zoning_prefixes: list[str] = field(default_factory=list)  # e.g. ["RM", "RD"]
    min_lot_sqft: float | None = None
    max_lot_sqft: float | None = None
    min_units: int | None = None
    min_residual: float | None = None  # max land offer floor (deal must pencil)
    exclude_high_flood_risk: bool = False
    require_verified: bool = False  # drop provisional/uncorroborated extractions
    max_results: int = 25


@dataclass
class ScreeningResult:
    """Outcome for one screened address."""

    address: str
    status: str = "rejected"  # "qualified" | "rejected" | "error"
    score: float = 0.0  # ranking score = residual max land offer
    max_units: int = 0
    max_land_price: float = 0.0
    zoning_district: str = ""
    county: str = ""
    state: str = ""
    lot_size_sqft: float = 0.0
    offer_is_provisional: bool = False
    reasons: list[str] = field(default_factory=list)  # why rejected
    error: str = ""


@dataclass
class BatchScreeningResult:
    """Aggregate screening outcome, with qualified deals ranked best-first."""

    qualified: list[ScreeningResult] = field(default_factory=list)
    rejected: list[ScreeningResult] = field(default_factory=list)
    errors: list[ScreeningResult] = field(default_factory=list)
    total: int = 0
    qualified_count: int = 0


def _norm_county(county: str) -> str:
    c = (county or "").strip().lower()
    return c[: -len(" county")].strip() if c.endswith(" county") else c


def evaluate_buy_box(report: ZoningReport, buy_box: BuyBox) -> ScreeningResult:
    """Evaluate one analyzed report against the buy box (pure, deterministic)."""
    prop = report.property_record
    density = report.density_analysis
    pf = report.pro_forma
    ver = report.extraction_verification

    lot_sqft = prop.lot_size_sqft if prop else 0.0
    max_units = density.max_units if density else 0
    max_land_price = pf.max_land_price if pf else 0.0
    provisional = bool(ver.offer_is_provisional) if ver else False

    result = ScreeningResult(
        address=report.address,
        score=max_land_price,
        max_units=max_units,
        max_land_price=max_land_price,
        zoning_district=report.zoning_district,
        county=report.county,
        state=report.state,
        lot_size_sqft=lot_sqft,
        offer_is_provisional=provisional,
    )

    reasons: list[str] = []

    if buy_box.states:
        wanted = {s.strip().upper() for s in buy_box.states}
        if (report.state or "").upper() not in wanted:
            reasons.append(f"State {report.state or '?'} not in target {sorted(wanted)}")

    if buy_box.counties:
        wanted_c = {_norm_county(c) for c in buy_box.counties}
        if _norm_county(report.county) not in wanted_c:
            reasons.append(f"County {report.county or '?'} not in target list")

    if buy_box.zoning_prefixes:
        district = (report.zoning_district or "").upper()
        if not any(district.startswith(p.strip().upper()) for p in buy_box.zoning_prefixes):
            reasons.append(f"Zoning {report.zoning_district or '?'} not in target types")

    if buy_box.min_lot_sqft is not None and lot_sqft < buy_box.min_lot_sqft:
        reasons.append(f"Lot {lot_sqft:,.0f} sqft below min {buy_box.min_lot_sqft:,.0f}")
    if buy_box.max_lot_sqft is not None and lot_sqft > buy_box.max_lot_sqft:
        reasons.append(f"Lot {lot_sqft:,.0f} sqft above max {buy_box.max_lot_sqft:,.0f}")

    if buy_box.min_units is not None and max_units < buy_box.min_units:
        reasons.append(f"Max units {max_units} below min {buy_box.min_units}")

    if buy_box.min_residual is not None and max_land_price < buy_box.min_residual:
        reasons.append(f"Residual ${max_land_price:,.0f} below min ${buy_box.min_residual:,.0f}")

    if buy_box.exclude_high_flood_risk and report.site_risk:
        if (report.site_risk.overall_risk or "").lower() == "high":
            reasons.append("High flood risk")

    if buy_box.require_verified and provisional:
        reasons.append("Buildable-unit drivers unverified (provisional)")

    result.reasons = reasons
    result.status = "qualified" if not reasons else "rejected"
    return result


def _assemble(results: list[ScreeningResult], buy_box: BuyBox) -> BatchScreeningResult:
    """Split, rank qualified deals best-first, and cap to max_results."""
    qualified = [r for r in results if r.status == "qualified"]
    rejected = [r for r in results if r.status == "rejected"]
    errors = [r for r in results if r.status == "error"]
    qualified.sort(key=lambda r: r.score, reverse=True)
    if buy_box.max_results > 0:
        qualified = qualified[: buy_box.max_results]
    return BatchScreeningResult(
        qualified=qualified,
        rejected=rejected,
        errors=errors,
        total=len(results),
        qualified_count=len(qualified),
    )


def screen_reports(reports: list[ZoningReport], buy_box: BuyBox) -> BatchScreeningResult:
    """Screen already-analyzed reports against the buy box (pure)."""
    results = [evaluate_buy_box(r, buy_box) for r in reports]
    return _assemble(results, buy_box)


async def screen_addresses(
    addresses: list[str],
    buy_box: BuyBox,
    analyze_fn: AnalyzeFn,
    *,
    concurrency: int = 4,
    per_item_timeout: float = 120.0,
    on_result: Callable[[ScreeningResult], Awaitable[None]] | None = None,
) -> BatchScreeningResult:
    """Analyze and screen many addresses with bounded concurrency.

    Each address is isolated: a timeout or exception yields an ``error`` result
    rather than failing the batch. ``on_result`` (if given) is awaited as each
    address completes — used by the API layer to stream progress.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(address: str) -> ScreeningResult:
        async with semaphore:
            try:
                report = await asyncio.wait_for(analyze_fn(address), timeout=per_item_timeout)
            except TimeoutError:
                result = ScreeningResult(address=address, status="error", error="timeout")
            except Exception as exc:  # isolate per-item failures
                logger.warning("Screening failed for %s: %s", address[:60], exc)
                result = ScreeningResult(address=address, status="error", error=str(exc))
            else:
                if report is None:
                    result = ScreeningResult(
                        address=address, status="error", error="could not analyze address"
                    )
                else:
                    result = evaluate_buy_box(report, buy_box)
            if on_result is not None:
                await on_result(result)
            return result

    results = await asyncio.gather(*(_one(a) for a in addresses))
    return _assemble(list(results), buy_box)
