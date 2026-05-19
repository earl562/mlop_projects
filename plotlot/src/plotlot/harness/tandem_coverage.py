"""Live MCP coverage runner for OpenData + Municode tandem workflows."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import uuid
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any, Literal

import httpx

from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.ingestion.discovery import get_municode_configs
from plotlot.land_use.models import ToolContext

CENSUS_COUNTY_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_counties_national.zip"
)
SUPPORTED_STATE_FIPS = {"CA": "06", "FL": "12", "NC": "37"}
ORDINANCE_QUERIES = ("setback", "permitted use", "yard")
PropertySearchMode = Literal["skip", "when-open-data", "all"]


@dataclass(frozen=True)
class CountySeed:
    state: str
    state_fips: str
    geoid: str
    county: str
    county_label: str
    lat: float
    lng: float


async def fetch_county_seeds(states: list[str]) -> list[CountySeed]:
    """Fetch county names and internal points from the Census Gazetteer."""

    wanted = {state.upper() for state in states}
    unknown = sorted(wanted - set(SUPPORTED_STATE_FIPS))
    if unknown:
        raise ValueError(f"Unsupported states for tandem coverage: {', '.join(unknown)}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(CENSUS_COUNTY_GAZETTEER_URL)
        response.raise_for_status()

    seeds: list[CountySeed] = []
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        [member] = archive.namelist()
        with archive.open(member) as raw_file:
            reader = csv.DictReader(TextIOWrapper(raw_file, encoding="utf-8"), delimiter="|")
            for row in reader:
                state = str(row["USPS"]).upper()
                if state not in wanted:
                    continue
                county_label = str(row["NAME"]).strip()
                county = county_label.removesuffix(" County").strip()
                seeds.append(
                    CountySeed(
                        state=state,
                        state_fips=str(row["GEOID"])[:2],
                        geoid=str(row["GEOID"]),
                        county=county,
                        county_label=county_label,
                        lat=float(row["INTPTLAT"]),
                        lng=float(row["INTPTLONG"]),
                    )
                )

    return sorted(seeds, key=lambda item: (item.state, item.county))


def _base_context(run_id: str) -> ToolContext:
    return ToolContext(
        workspace_id="mcp_tandem_coverage",
        actor_user_id="codex",
        run_id=run_id,
        project_id="mcp_tandem_coverage",
        risk_budget_cents=10_000,
        live_network_allowed=True,
        approved_approval_ids=set(),
    )


async def _call_mcp_tool(
    adapter: MCPAdapter,
    *,
    name: str,
    arguments: dict[str, Any],
    run_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    context = _base_context(run_id)
    try:
        result = await asyncio.wait_for(
            adapter.call_tool(name=name, arguments=arguments, context=context),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return {
            "transport_status": "timeout",
            "tool_status": "timeout",
            "message": f"{name} exceeded {timeout_seconds:.0f}s",
            "result_count": 0,
        }

    payload = result.result or {}
    results = payload.get("results")
    result_count = len(results) if isinstance(results, list) else 0
    if name == "search_properties":
        result_count = int(payload.get("total_results") or 0)
    return {
        "transport_status": result.status,
        "tool_status": payload.get("status") or result.status,
        "message": payload.get("message") or result.message,
        "result_count": result_count,
        "payload": payload,
    }


def _sample_payload(payload: dict[str, Any], *, max_items: int = 3) -> dict[str, Any]:
    sampled = dict(payload)
    if isinstance(sampled.get("results"), list):
        sampled["results"] = sampled["results"][:max_items]
    if isinstance(sampled.get("sample"), list):
        sampled["sample"] = sampled["sample"][:max_items]
    if isinstance(sampled.get("evidence"), list):
        sampled["evidence"] = sampled["evidence"][:1]
    return sampled


def _classify_county(
    *,
    layer_count: int,
    property_status: str,
    property_count: int,
    authority_count: int,
    ordinance_hit_count: int,
) -> str:
    if (
        layer_count > 0
        and property_status == "success"
        and property_count > 0
        and authority_count > 0
        and ordinance_hit_count > 0
    ):
        return "ok"
    if layer_count > 0 and authority_count == 0:
        return "partial_no_municode_authority"
    if layer_count > 0 and authority_count > 0 and ordinance_hit_count == 0:
        return "partial_no_ordinance_hits"
    if layer_count > 0 and authority_count > 0 and property_status == "success":
        return "partial_no_property_matches"
    if layer_count > 0 and authority_count > 0:
        return "partial_property_search_error"
    if layer_count == 0 and authority_count > 0:
        return "partial_no_open_data_layers"
    return "unsupported_or_no_public_coverage"


async def evaluate_county(
    adapter: MCPAdapter,
    seed: CountySeed,
    *,
    property_search: PropertySearchMode,
    timeout_seconds: float,
) -> dict[str, Any]:
    run_prefix = f"mcp_tandem_{seed.state.lower()}_{seed.geoid}_{uuid.uuid4().hex[:8]}"
    common_args = {
        "county": seed.county,
        "state": seed.state,
        "lat": seed.lat,
        "lng": seed.lng,
    }

    open_data = await _call_mcp_tool(
        adapter,
        name="discover_open_data_layers",
        arguments=common_args,
        run_id=f"{run_prefix}_opendata",
        timeout_seconds=timeout_seconds,
    )
    layer_count = open_data["result_count"]

    should_search_property = property_search == "all" or (
        property_search == "when-open-data" and layer_count > 0
    )
    if should_search_property:
        property_result = await _call_mcp_tool(
            adapter,
            name="search_properties",
            arguments={**common_args, "max_results": 1},
            run_id=f"{run_prefix}_property",
            timeout_seconds=timeout_seconds,
        )
    else:
        property_result = {
            "transport_status": "skipped",
            "tool_status": "skipped",
            "message": "Skipped because no OpenData layer was discovered first.",
            "result_count": 0,
            "payload": {},
        }

    authorities = await _call_mcp_tool(
        adapter,
        name="discover_municode_authorities",
        arguments={"county": seed.county, "state": seed.state},
        run_id=f"{run_prefix}_municode_authorities",
        timeout_seconds=timeout_seconds,
    )
    authority_payload = authorities.get("payload") or {}
    authority_results = authority_payload.get("results") or []

    ordinance_searches: list[dict[str, Any]] = []
    if authority_results:
        authority_name = str(authority_results[0].get("municipality") or "")
        for query in ORDINANCE_QUERIES:
            ordinance_searches.append(
                await _call_mcp_tool(
                    adapter,
                    name="search_municode_live",
                    arguments={
                        "municipality": authority_name,
                        "state": seed.state,
                        "query": query,
                        "limit": 3,
                    },
                    run_id=f"{run_prefix}_municode_{query.replace(' ', '_')}",
                    timeout_seconds=timeout_seconds,
                )
            )

    ordinance_hit_count = sum(search["result_count"] for search in ordinance_searches)
    tandem_status = _classify_county(
        layer_count=layer_count,
        property_status=str(property_result["tool_status"]),
        property_count=property_result["result_count"],
        authority_count=len(authority_results),
        ordinance_hit_count=ordinance_hit_count,
    )

    return {
        "county": asdict(seed),
        "tandem_status": tandem_status,
        "open_data": {
            **{k: v for k, v in open_data.items() if k != "payload"},
            "sample": _sample_payload(open_data.get("payload") or {}),
        },
        "property_search": {
            **{k: v for k, v in property_result.items() if k != "payload"},
            "sample": _sample_payload(property_result.get("payload") or {}),
        },
        "municode_authorities": {
            **{k: v for k, v in authorities.items() if k != "payload"},
            "sample": _sample_payload(authority_payload),
        },
        "municode_searches": [
            {
                **{k: v for k, v in search.items() if k != "payload"},
                "sample": _sample_payload(search.get("payload") or {}),
            }
            for search in ordinance_searches
        ],
    }


async def run_coverage(
    *,
    states: list[str],
    counties: list[str] | None = None,
    limit: int | None = None,
    concurrency: int = 4,
    property_search: PropertySearchMode = "when-open-data",
    timeout_seconds: float = 90.0,
    refresh_municode: bool = False,
) -> dict[str, Any]:
    seeds = await fetch_county_seeds(states)
    if counties:
        wanted = {county.strip().lower() for county in counties}
        seeds = [seed for seed in seeds if seed.county.lower() in wanted]
    if limit is not None:
        seeds = seeds[:limit]

    # Warm the Municode cache once before per-county MCP calls fan out.
    await get_municode_configs(force_refresh=refresh_municode)

    adapter = MCPAdapter(get_default_runtime())
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(seed: CountySeed) -> dict[str, Any]:
        async with semaphore:
            try:
                return await evaluate_county(
                    adapter,
                    seed,
                    property_search=property_search,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                return {
                    "county": asdict(seed),
                    "tandem_status": "runner_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }

    started_at = datetime.now(timezone.utc)
    results = await asyncio.gather(*[_bounded(seed) for seed in seeds])
    completed_at = datetime.now(timezone.utc)
    counts = Counter(str(result.get("tandem_status")) for result in results)

    return {
        "schema_version": 1,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 2),
        "states": sorted({state.upper() for state in states}),
        "county_count": len(results),
        "property_search": property_search,
        "summary": dict(sorted(counts.items())),
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", nargs="+", default=["FL", "NC", "CA"])
    parser.add_argument("--county", action="append", dest="counties")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--property-search",
        choices=["skip", "when-open-data", "all"],
        default="when-open-data",
    )
    parser.add_argument("--refresh-municode", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/status/mcp-tandem-county-coverage.json"),
    )
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


async def _async_main() -> int:
    args = _parse_args()
    payload = await run_coverage(
        states=args.states,
        counties=args.counties,
        limit=args.limit,
        concurrency=max(1, args.concurrency),
        property_search=args.property_search,
        timeout_seconds=args.timeout,
        refresh_municode=args.refresh_municode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), **payload["summary"]}, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
