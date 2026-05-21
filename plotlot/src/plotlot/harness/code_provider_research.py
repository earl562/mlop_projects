"""Research code providers for counties where the Municode zoning scanner failed."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.land_use.models import ToolContext


def _base_context(run_id: str) -> ToolContext:
    return ToolContext(
        workspace_id="mcp_code_provider_research",
        actor_user_id="codex",
        run_id=run_id,
        project_id="mcp_code_provider_research",
        risk_budget_cents=10_000,
        live_network_allowed=True,
        approved_approval_ids=set(),
    )


def counties_missing_municode_authority(coverage: dict[str, Any]) -> list[dict[str, str]]:
    counties: list[dict[str, str]] = []
    for result in coverage.get("results", []):
        municode = result.get("municode_authorities") or {}
        if int(municode.get("result_count") or 0) > 0:
            continue
        county = result.get("county") or {}
        counties.append(
            {
                "state": str(county.get("state") or ""),
                "county": str(county.get("county") or ""),
                "geoid": str(county.get("geoid") or ""),
            }
        )
    return sorted(counties, key=lambda item: (item["state"], item["county"]))


async def _call_discovery(
    adapter: MCPAdapter,
    *,
    county: str,
    state: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            adapter.call_tool(
                name="discover_code_authorities",
                arguments={"county": county, "state": state, "include_web_fallback": True},
                context=_base_context(
                    f"code_provider_{state.lower()}_{county.lower().replace(' ', '_')}"
                ),
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return {
            "status": "timeout",
            "results": [],
            "message": f"discover_code_authorities exceeded {timeout_seconds:.0f}s",
        }

    payload = result.result or {}
    return {
        "status": payload.get("status") or result.status,
        "results": payload.get("results") or [],
        "message": payload.get("message") or result.message,
    }


async def run_research(
    *,
    coverage_path: Path,
    concurrency: int = 4,
    timeout_seconds: float = 45.0,
    retry_misses: int = 1,
) -> dict[str, Any]:
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    counties = counties_missing_municode_authority(coverage)
    adapter = MCPAdapter(get_default_runtime())
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(item: dict[str, str]) -> dict[str, Any]:
        async with semaphore:
            discovery = await _call_discovery(
                adapter,
                county=item["county"],
                state=item["state"],
                timeout_seconds=timeout_seconds,
            )
            results = list(discovery.get("results") or [])
            primary = results[0] if results else None
            return {
                **item,
                "status": discovery["status"],
                "provider_found": bool(results),
                "primary_platform": primary.get("platform") if primary else None,
                "primary_publisher": primary.get("publisher") if primary else None,
                "primary_source_url": primary.get("source_url") if primary else None,
                "primary_confidence": primary.get("confidence") if primary else None,
                "sources": results,
                "message": discovery.get("message"),
                "retry_round": 0,
            }

    started_at = datetime.now(timezone.utc)
    results = await asyncio.gather(*[_bounded(item) for item in counties])

    for retry_round in range(1, max(0, retry_misses) + 1):
        missing_indexes = [
            index for index, result in enumerate(results) if not result["provider_found"]
        ]
        if not missing_indexes:
            break

        await asyncio.sleep(0.5)
        retry_results = await asyncio.gather(
            *[_bounded(counties[index]) for index in missing_indexes]
        )
        for index, retry_result in zip(missing_indexes, retry_results, strict=True):
            if retry_result["provider_found"]:
                retry_result["retry_round"] = retry_round
                results[index] = retry_result

    completed_at = datetime.now(timezone.utc)

    platform_counts = Counter(
        str(result.get("primary_platform") or "not_found") for result in results
    )
    by_state: dict[str, dict[str, int]] = {}
    state_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        state_counts[str(result["state"])][str(result.get("primary_platform") or "not_found")] += 1
    by_state = {
        state: dict(sorted(counter.items())) for state, counter in sorted(state_counts.items())
    }

    return {
        "schema_version": 1,
        "source_coverage_path": str(coverage_path),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 2),
        "county_count": len(results),
        "summary": dict(sorted(platform_counts.items())),
        "summary_by_state": by_state,
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("docs/status/mcp-tandem-county-coverage.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/status/non-municode-code-provider-research.json"),
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retry-misses", type=int, default=1)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


async def _async_main() -> int:
    args = _parse_args()
    payload = await run_research(
        coverage_path=args.coverage,
        concurrency=max(1, args.concurrency),
        timeout_seconds=args.timeout,
        retry_misses=max(0, args.retry_misses),
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
