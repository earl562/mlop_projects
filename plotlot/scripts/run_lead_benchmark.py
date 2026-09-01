#!/usr/bin/env python3
"""Plan or execute the governed PlotLot harness against sanitized lead cases."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from plotlot.evaluation.benchmark import build_plan_benchmark, run_live_benchmark
from plotlot.evaluation.leads import load_lead_fixture
from plotlot.harness.agents import MultiAgentCoordinator
from plotlot.harness.default_runtime import get_default_runtime


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "leads"
    / "plotlot_drive_leads.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark PlotLot against a property-only Drive-derived corpus."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--disable-live-network", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> str:
    cases = load_lead_fixture(args.fixture)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        cases = cases[: args.limit]

    if args.execute:
        summary = await run_live_benchmark(
            cases,
            coordinator=MultiAgentCoordinator(get_default_runtime()),
            live_network_allowed=not args.disable_live_network,
        )
    else:
        summary = build_plan_benchmark(cases)
    return summary.model_dump_json(indent=2)


def main() -> int:
    args = build_parser().parse_args()
    payload = asyncio.run(_run(args)) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Wrote benchmark output to {args.output}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
