"""Harness optimization loop — automated search over harness configurations.

Per Meta-Harness (Stanford, arXiv 2603.28052):
- Coding-agent proposer with filesystem access to prior candidates
- Each candidate: source code, eval scores, execution traces
- Proposer reads median 82 files/iteration, references 20+ prior candidates
- Up to 10M tokens diagnostic context vs 26K for prior methods
- No parent-selection rule: proposer freely inspects any prior harness

Per Better Harness (LangChain): evals are training data. Holdout sets prevent overfitting.
Per Image 2 (Obsidian vault): "Every eval data point is the agent equivalent of a training gradient."

Architecture:
1. Candidate harnesses stored as directories in .sisyphus/optimizer/
2. Each directory: harness_config.json, scores.json, traces.jsonl
3. Proposer (coding agent) inspects prior candidates, proposes new configs
4. Eval runner: execute harness against eval suite, compute scores
5. Pareto frontier: track non-dominated candidates
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CandidateHarness:
    id: str
    config: dict[str, Any]
    scores: dict[str, float] = field(default_factory=dict)
    traces_path: str = ""
    iteration: int = 0
    parent_id: str | None = None

    def dominates(self, other: "CandidateHarness") -> bool:
        """Returns True if self dominates other (better on all metrics)."""
        if not self.scores or not other.scores:
            return False
        all_keys = set(self.scores.keys()) | set(other.scores.keys())
        better = False
        for key in all_keys:
            a = self.scores.get(key, 0.0)
            b = other.scores.get(key, 0.0)
            if a < b:
                return False
            if a > b:
                better = True
        return better


class HarnessOptimizer:
    """Outer-loop optimizer that searches over harness configurations.

    Usage:
        optimizer = HarnessOptimizer(workspace=".sisyphus/optimizer")
        optimizer.add_candidate({"middleware": ["TokenAware"], "system_prompt": "..."})
        optimizer.evaluate(candidate_id, eval_fn)
        frontier = optimizer.pareto_frontier()
    """

    def __init__(self, workspace: str = ".sisyphus/optimizer"):
        self._workspace = workspace
        self._candidates: dict[str, CandidateHarness] = {}
        os.makedirs(workspace, exist_ok=True)

    def add_candidate(self, config: dict[str, Any], parent_id: str | None = None) -> str:
        cid = f"candidate-{len(self._candidates):04d}"
        candidate = CandidateHarness(
            id=cid,
            config=config,
            iteration=len(self._candidates),
            parent_id=parent_id,
        )
        self._candidates[cid] = candidate
        self._save_candidate(candidate)
        return cid

    def get_candidate(self, cid: str) -> CandidateHarness | None:
        return self._candidates.get(cid)

    def record_scores(self, cid: str, scores: dict[str, float]) -> None:
        if cid in self._candidates:
            self._candidates[cid].scores = scores
            self._save_candidate(self._candidates[cid])

    def record_traces(self, cid: str, traces: list[dict[str, Any]]) -> None:
        if cid in self._candidates:
            c = self._candidates[cid]
            c.traces_path = os.path.join(self._workspace, cid, "traces.jsonl")
            os.makedirs(os.path.dirname(c.traces_path), exist_ok=True)
            with open(c.traces_path, "w") as f:
                for t in traces:
                    f.write(json.dumps(t) + "\n")

    def pareto_frontier(self) -> list[CandidateHarness]:
        """Return non-dominated candidates sorted by iteration."""
        frontier: list[CandidateHarness] = []
        for c in self._candidates.values():
            if not c.scores:
                continue
            dominated = any(other.dominates(c) for other in self._candidates.values() if other.id != c.id and other.scores)
            if not dominated:
                frontier.append(c)
        return sorted(frontier, key=lambda c: c.iteration)

    def best_by(self, metric: str) -> CandidateHarness | None:
        scored = [c for c in self._candidates.values() if metric in c.scores]
        if not scored:
            return None
        return max(scored, key=lambda c: c.scores[metric])

    def export_summary(self) -> dict[str, Any]:
        return {
            "total_candidates": len(self._candidates),
            "pareto_frontier_count": len(self.pareto_frontier()),
            "best_scores": {m: (self.best_by(m).scores[m] if self.best_by(m) else None) for m in self._all_metrics()},
            "candidates": [
                {"id": c.id, "iteration": c.iteration, "scores": c.scores, "parent": c.parent_id}
                for c in sorted(self._candidates.values(), key=lambda c: c.iteration)
            ],
        }

    def _all_metrics(self) -> set[str]:
        metrics: set[str] = set()
        for c in self._candidates.values():
            metrics.update(c.scores.keys())
        return metrics

    def _save_candidate(self, candidate: CandidateHarness) -> None:
        dir_path = os.path.join(self._workspace, candidate.id)
        os.makedirs(dir_path, exist_ok=True)
        with open(os.path.join(dir_path, "harness_config.json"), "w") as f:
            json.dump({"id": candidate.id, "config": candidate.config, "scores": candidate.scores, "iteration": candidate.iteration, "parent_id": candidate.parent_id}, f, indent=2)


class EvalRunner:
    """Run a harness candidate against an eval suite and compute metrics."""

    def __init__(self, eval_cases: list[dict[str, Any]]):
        self._cases = eval_cases
        self._results: dict[str, list[dict[str, Any]]] = {}

    @property
    def cases(self) -> list[dict[str, Any]]:
        return list(self._cases)

    async def evaluate(self, harness_config: dict[str, Any], run_harness: Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        total_correct = 0
        total_latency = 0.0
        total_tokens = 0
        traces: list[dict[str, Any]] = []
        for case in self._cases:
            start = time.monotonic()
            result = await run_harness(harness_config, case)
            elapsed = time.monotonic() - start
            total_latency += elapsed
            total_tokens += result.get("tokens", 0)
            if result.get("correct"):
                total_correct += 1
            traces.append({"case": case.get("id", "unknown"), "correct": result.get("correct"), "latency": elapsed, "tokens": result.get("tokens", 0), "output": str(result.get("output", ""))[:500]})
        n = len(self._cases)
        scores["accuracy"] = total_correct / n if n > 0 else 0.0
        scores["avg_latency"] = total_latency / n if n > 0 else 0.0
        scores["avg_tokens"] = total_tokens / n if n > 0 else 0.0
        scores["solve_rate"] = total_correct / total_latency if total_latency > 0 else 0.0
        return scores


class OptimizationLoop:
    """Run the full Meta-Harness optimization loop.

    Loop: propose → evaluate → record → repeat.
    Proposer inspects all prior candidates and their traces to propose next config.
    """

    def __init__(
        self,
        optimizer: HarnessOptimizer,
        evaluator: EvalRunner,
        run_harness: Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]],
        propose: Callable[[HarnessOptimizer], Awaitable[dict[str, Any]]],
        max_iterations: int = 20,
    ):
        self._optimizer = optimizer
        self._evaluator = evaluator
        self._run_harness = run_harness
        self._propose = propose
        self._max = max_iterations

    async def run(self) -> HarnessOptimizer:
        for i in range(self._max):
            config = await self._propose(self._optimizer)
            cid = self._optimizer.add_candidate(config, parent_id=None)
            scores = await self._evaluator.evaluate(config, self._run_harness)
            self._optimizer.record_scores(cid, scores)
            frontier = self._optimizer.pareto_frontier()
            if frontier and scores.get("accuracy", 0) >= 0.95:
                break
        return self._optimizer
