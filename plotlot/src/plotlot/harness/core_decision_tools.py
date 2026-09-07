"""Transport-neutral deterministic decision tools for the PlotLot harness.

These handlers are the shared execution seam for REST, MCP, chat, and future
agent-run adapters. They call existing deterministic domain functions and never
depend on HTTP requests, SSE envelopes, browser state, or chat session memory.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from plotlot.harness.runtime import HarnessRuntime
from plotlot.land_use.models import ToolContext

MAX_SCREEN_ADDRESSES = 20


def _jsonable(value: Any) -> Any:
    """Convert dataclass/Pydantic-rich domain values into JSON-compatible values."""

    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(cast(Any, value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _optional_number(args: dict[str, Any], key: str) -> float | None:
    value = args.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _positive_int(args: dict[str, Any], key: str) -> int | None:
    value = args.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return int(value)
    return None


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


async def handle_calculate(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Evaluate arithmetic with the sandboxed deterministic calculator."""

    del context
    from plotlot.pipeline.safe_calc import CalcError, safe_calculate

    expression = str(args.get("expression") or "").strip()
    if not expression:
        return {
            "status": "error",
            "expression": expression,
            "message": "expression is required",
        }

    try:
        result = safe_calculate(expression)
    except CalcError as exc:
        return {
            "status": "error",
            "expression": expression,
            "message": (
                f"Could not evaluate the expression: {exc}. "
                "Pass arithmetic only using numbers, parentheses, and + - * / // % **."
            )[:300],
        }

    value: float | int = int(result) if result == int(result) else round(result, 4)
    return {"status": "success", "expression": expression, "result": value}


def _serialize_upzoning_scenario(scenario: Any) -> dict[str, Any] | None:
    if scenario is None:
        return None
    return {
        "name": scenario.name,
        "yield_count": scenario.yield_count,
        "yield_basis": scenario.yield_basis,
        "value_per_yield": round(scenario.value_per_yield),
        "gross_value": round(scenario.gross_value),
        "instant_equity": round(scenario.instant_equity),
        "formula": scenario.formula,
    }


async def handle_analyze_upzoning(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Compare by-right and target entitlement yields using supplied inputs only."""

    del context
    from plotlot.pipeline.upzoning import analyze_upzoning

    lot_sqft = _optional_number(args, "lot_sqft")
    if not lot_sqft or lot_sqft <= 0:
        return {
            "status": "error",
            "message": "A positive lot_sqft is required for upzoning analysis.",
        }

    analysis = analyze_upzoning(
        lot_sqft=lot_sqft,
        value_per_lot=_optional_number(args, "value_per_lot"),
        purchase_price=_optional_number(args, "purchase_price") or 0.0,
        entitlement_soft_costs=_optional_number(args, "entitlement_soft_costs") or 0.0,
        baseline_yield=_positive_int(args, "baseline_yield"),
        upzoned_yield=_positive_int(args, "upzoned_yield"),
        baseline_min_lot_area_sqft=_optional_number(args, "baseline_min_lot_area_sqft"),
        upzoned_min_lot_area_sqft=_optional_number(args, "upzoned_min_lot_area_sqft"),
        yield_basis=str(args.get("yield_basis") or "buildable lots"),
        min_lot_width_ft=_optional_number(args, "min_lot_width_ft"),
        lot_frontage_ft=_optional_number(args, "lot_frontage_ft"),
        value_source="comps" if args.get("value_source") == "comps" else "override",
    )

    return {
        "status": "success",
        "all_in_basis": round(analysis.all_in_basis),
        "value_source": analysis.value_source,
        "baseline": _serialize_upzoning_scenario(analysis.baseline),
        "upzoned": _serialize_upzoning_scenario(analysis.upzoned),
        "value_uplift": round(analysis.value_uplift),
        "equity_created": round(analysis.equity_created),
        "cost_per_yield": round(analysis.cost_per_yield),
        "exit_options": list(analysis.exit_options),
        "notes": list(analysis.notes),
        "warnings": list(analysis.warnings),
        "grounding_note": (
            "Equity is calculated only from the supplied target yield, per-yield value, "
            "purchase price, and entitlement costs. Missing values are not estimated."
        ),
    }


def serialize_analysis_report(report: Any) -> dict[str, Any]:
    """Shape a deep deterministic report into the stable agent decision contract."""

    property_record = report.property_record
    density = report.density_analysis
    verification = report.extraction_verification
    comps = report.comp_analysis
    pro_forma = report.pro_forma

    by_right = {
        "max_units": density.max_units if density else None,
        "governing_constraint": density.governing_constraint if density else "unknown",
        "confidence": density.confidence if density else "low",
        "origin": density.origin if density else "unknown",
        "verification": verification.overall if verification else "unverified",
        "offer_is_provisional": (verification.offer_is_provisional if verification else True),
        "constraints": _jsonable(density.constraints) if density else [],
        "notes": list(density.notes) if density else [],
    }

    adv_per_unit = None
    adv_source = ""
    if pro_forma is not None:
        adv_per_unit = pro_forma.adv_per_unit
        adv_source = pro_forma.adv_source
    elif comps is not None:
        adv_per_unit = comps.adv_per_unit
        adv_source = comps.adv_source

    valuation = {
        "estimated_land_value": comps.estimated_land_value if comps else None,
        "land_value_range": (
            [comps.estimated_land_value_low, comps.estimated_land_value_high] if comps else None
        ),
        "adv_per_unit": adv_per_unit,
        "adv_source": adv_source,
        "gross_development_value": (pro_forma.gross_development_value if pro_forma else None),
        "max_land_price_residual": pro_forma.max_land_price if pro_forma else None,
        "impact_fees_per_unit": pro_forma.impact_fees_per_unit if pro_forma else None,
        "cost_per_door": pro_forma.cost_per_door if pro_forma else None,
        "construction_cost_psf": (pro_forma.construction_cost_psf if pro_forma else None),
        "market": pro_forma.market if pro_forma else "",
    }

    return {
        "status": "success",
        "address": report.formatted_address or report.address,
        "municipality": report.municipality,
        "county": report.county,
        "state": report.state,
        "lat": report.lat,
        "lng": report.lng,
        "zoning_code": report.zoning_district,
        "zoning_description": report.zoning_description,
        "allowed_uses": list(report.allowed_uses),
        "conditional_uses": list(report.conditional_uses),
        "prohibited_uses": list(report.prohibited_uses),
        "owner": property_record.owner if property_record else "",
        "lot_size_sqft": property_record.lot_size_sqft if property_record else None,
        "lot_size_source": property_record.lot_size_source if property_record else "",
        "property_record": _jsonable(property_record),
        "by_right": by_right,
        "valuation": valuation,
        "sensitivity": _jsonable(report.sensitivity),
        "entitlement": _jsonable(report.entitlement),
        "site_risk": _jsonable(report.site_risk),
        "coastal_height_overlay": _jsonable(report.coastal_overlay),
        "ca_upside": _jsonable(report.density_uplift),
        "development_activity": _jsonable(report.development_signals) or {},
        "entitlement_timeline_risk": _jsonable(report.entitlement_timeline_risk),
        "opposition_risk": _jsonable(report.opposition_risk),
        "source_refs": _jsonable(report.source_refs) or [],
        "claims": _jsonable(report.claims) or [],
        "warnings": list(report.warnings),
        "sources": list(report.sources),
        "confidence": report.confidence,
    }


async def handle_analyze_property(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Run the existing deep deterministic property pipeline for one address."""

    del context
    from plotlot.pipeline.analyze import analyze_property_deep

    address = str(args.get("address") or "").strip()
    if not address:
        return {"status": "error", "message": "An address is required."}

    try:
        report = await analyze_property_deep(address)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Analysis failed: {type(exc).__name__}: {exc}"[:300],
        }

    if report is None:
        return {"status": "not_found", "message": f"Could not analyze: {address}"}
    return serialize_analysis_report(report)


def _normalized_addresses(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []

    unique: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            continue
        address = value.strip()
        key = address.casefold()
        if not address or key in seen:
            continue
        seen.add(key)
        unique.append(address)
        if len(unique) >= MAX_SCREEN_ADDRESSES:
            break
    return unique


def _screening_row(result: Any) -> dict[str, Any]:
    return {
        "address": result.address,
        "score": round(result.score),
        "max_units": result.max_units,
        "max_land_price": (
            round(result.max_land_price) if result.max_land_price is not None else None
        ),
        "zoning": result.zoning_district,
        "county": result.county,
        "state": result.state,
        "lot_size_sqft": result.lot_size_sqft,
        "offer_is_provisional": result.offer_is_provisional,
        "reasons": list(result.reasons),
    }


async def handle_screen_properties(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Screen a bounded address set against a deterministic acquisition buy box."""

    del context
    from plotlot.pipeline.analyze import analyze_property_full
    from plotlot.pipeline.screening import BuyBox, screen_addresses

    addresses = _normalized_addresses(args.get("addresses"))
    if not addresses:
        return {
            "status": "error",
            "message": "Provide at least one address to screen.",
        }

    buy_box = BuyBox(
        states=args.get("states") or [],
        counties=args.get("counties") or [],
        zoning_prefixes=args.get("zoning_prefixes") or [],
        min_lot_sqft=args.get("min_lot_sqft"),
        max_lot_sqft=args.get("max_lot_sqft"),
        min_units=args.get("min_units"),
        min_residual=args.get("min_residual"),
        exclude_high_flood_risk=bool(args.get("exclude_high_flood_risk", False)),
        require_verified=bool(args.get("require_verified", False)),
        max_results=_bounded_int(
            args.get("max_results"),
            default=25,
            minimum=1,
            maximum=100,
        ),
    )

    async def analyze(address: str):
        return await analyze_property_full(address, with_comps=False)

    try:
        batch = await screen_addresses(
            addresses,
            buy_box,
            analyze,
            concurrency=4,
            per_item_timeout=90.0,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Screening failed: {type(exc).__name__}: {exc}"[:300],
        }

    return {
        "status": "success",
        "screened": batch.total,
        "qualified_count": batch.qualified_count,
        "qualified": [_screening_row(item) for item in batch.qualified],
        "rejected_count": len(batch.rejected),
        "rejected_sample": [
            {
                "address": item.address,
                "reasons": list(item.reasons),
            }
            for item in batch.rejected[:5]
        ],
        "error_count": len(batch.errors),
        "error_sample": [
            {
                "address": item.address,
                "error": item.error,
            }
            for item in batch.errors[:5]
        ],
        "grounding_note": (
            "Rankings come from the deterministic residual offer. "
            "Rows marked offer_is_provisional rely on unverified unit drivers."
        ),
    }


def register_core_decision_tools(runtime: HarnessRuntime) -> None:
    """Register the core product decisions on a shared harness runtime."""

    runtime.register("analyze_property", handle_analyze_property)
    runtime.register("calculate", handle_calculate)
    runtime.register("analyze_upzoning", handle_analyze_upzoning)
    runtime.register("screen_properties", handle_screen_properties)
