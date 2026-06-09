"""Phase 9: Production hardening — garbage collection, canary deploys, RLM wrapper.

Per OpenAI Harness Engineering: "Garbage collection" — background Codex tasks scan for deviations,
open targeted refactoring PRs. Golden principles encoded as mechanical checks.

Per RLMs (arXiv 2512.24601): recursive decomposition for long-context tasks.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenPrinciple:
    name: str
    description: str
    check_pattern: str  # simple string match against file content
    fix_suggestion: str


DEFAULT_PRINCIPLES = [
    GoldenPrinciple("no_raw_dicts", "Use Pydantic models, not raw dicts", "dict[str, Any]", "Replace with Pydantic BaseModel"),
    GoldenPrinciple("async_first", "I/O must be async", "import requests", "Use httpx.AsyncClient"),
    GoldenPrinciple("no_print", "No print() in library code", "print(", "Use structlog or logging"),
]


class GarbageCollector:
    """Scan workspace for deviations from golden principles, propose fixes."""

    def __init__(self, principles: list[GoldenPrinciple] | None = None):
        self._principles = principles or DEFAULT_PRINCIPLES

    def scan(self, workspace: str) -> list[dict[str, Any]]:
        deviations: list[dict[str, Any]] = []
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".venv")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = open(fpath).read()
                except Exception:
                    continue
                for p in self._principles:
                    if p.check_pattern in content:
                        deviations.append({"file": fpath, "principle": p.name, "description": p.description, "fix": p.fix_suggestion})
        return deviations

    def suggest_fixes(self, deviations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"file": d["file"], "action": d["fix"], "principle": d["principle"]} for d in deviations]

    def run_cleanup(self, workspace: str) -> dict[str, Any]:
        deviations = self.scan(workspace)
        return {"workspace": workspace, "deviations_found": len(deviations), "fixes": self.suggest_fixes(deviations), "principles_checked": len(self._principles)}


class CanaryDeploy:
    """Canary deployment with rollback capability."""

    def __init__(self):
        self._versions: dict[str, dict[str, Any]] = {}
        self._current: str | None = None
        self._traffic_split: float = 1.0  # fraction to new version

    def deploy(self, version: str, harness_config: dict[str, Any]) -> str:
        self._versions[version] = {"config": harness_config, "deployed_at": time.time(), "healthy": True}
        self._current = version
        self._traffic_split = 0.10  # start with 10%
        return version

    def rollback(self, version: str) -> bool:
        if version in self._versions:
            self._current = version
            self._traffic_split = 1.0
            return True
        return False

    def health_check(self) -> dict[str, Any]:
        return {"current": self._current, "healthy": self._versions.get(self._current or "", {}).get("healthy", False), "traffic_split_pct": round(self._traffic_split * 100, 1), "versions": list(self._versions.keys())}

    def set_traffic(self, pct_new: float) -> None:
        self._traffic_split = max(0.0, min(1.0, pct_new))

    def promote(self) -> None:
        self._traffic_split = 1.0


class RLMWrapper:
    """Recursive Language Models — decompose large contexts for model calls.

    Per RLM blog (Alex Zhang, MIT): "RLMs solve context rot by never exposing
    the full context to any single model call."
    """

    def __init__(self, model_caller: Any, max_depth: int = 3, max_chunk_size: int = 50000):
        self._call_model = model_caller
        self._max_depth = max_depth
        self._max_chunk = max_chunk_size

    def decompose(self, context: str, query: str) -> list[dict[str, Any]]:
        chunks = []
        lines = context.split("\n")
        current = ""
        for line in lines:
            if len(current) + len(line) > self._max_chunk and current:
                chunks.append({"text": current, "query": query})
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append({"text": current, "query": query})
        return chunks

    async def recursive_call(self, query: str, context: str, depth: int = 0) -> str:
        if depth >= self._max_depth or len(context) <= self._max_chunk:
            from plotlot.harness.middleware import AgentState
            state = AgentState()
            state.add_message("system", f"Answer: {query}")
            state.add_message("user", context[:self._max_chunk])
            result = await self._call_model(state, [])
            for msg in result.messages:
                if msg.get("role") == "assistant":
                    return msg.get("content", "")
            return ""
        chunks = self.decompose(context, query)
        partials: list[str] = []
        for chunk in chunks[:3]:
            result = await self.recursive_call(chunk["query"], chunk["text"], depth + 1)
            partials.append(result)
        combined = "\n".join(partials)
        return await self.recursive_call(query, combined, depth + 1)

    async def solve(self, query: str, context: str) -> str:
        if len(context) <= self._max_chunk:
            return await self.recursive_call(query, context, 0)
        return await self.recursive_call(query, context, 0)
