"""Tiered memory system — in-memory + optional PostgreSQL persistence.

Four tiers: WORKING (in-context), SHORT_TERM (AGENTS.md), MEDIUM_TERM (per-user DB),
LONG_TERM (org-level vector/graph).

Per GTM Agent blog: edit diffs → structured observations → compaction.
Per Your harness, your memory: memory is not a plugin — it IS the harness.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


class MemoryTier(str, Enum):
    WORKING = "working"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


@dataclass
class MemoryEntry:
    key: str
    value: Any
    tier: MemoryTier
    user_id: str | None = None
    project_id: str | None = None
    source: str = "unknown"
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class MemoryStore:
    """Tiered memory with in-memory backend + optional PostgreSQL persistence."""

    def __init__(self):
        self._entries: dict[str, list[MemoryEntry]] = defaultdict(list)
        self._observations: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def store(self, entry: MemoryEntry) -> None:
        namespace = self._namespace(entry.tier, entry.user_id, entry.project_id)
        self._entries[namespace].append(entry)

    def retrieve(self, tier: MemoryTier, user_id: str | None = None, project_id: str | None = None, key_prefix: str | None = None, limit: int = 10) -> list[MemoryEntry]:
        namespace = self._namespace(tier, user_id, project_id)
        entries = self._entries.get(namespace, [])
        if key_prefix:
            entries = [e for e in entries if e.key.startswith(key_prefix)]
        for e in entries:
            e.access_count += 1
        return sorted(entries, key=lambda e: e.created_at, reverse=True)[:limit]

    def store_observation(self, user_id: str, key: str, value: Any, source: str = "edit_diff") -> None:
        self._observations[user_id].append({"key": key, "value": value, "source": source, "at": time.time()})

    def get_observations(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._observations.get(user_id, [])[-limit:]

    def compact(self, user_id: str) -> int:
        obs = self._observations.get(user_id, [])
        seen: dict[str, dict[str, Any]] = {}
        for o in obs:
            key = o["key"]
            if key not in seen or o["at"] > seen[key]["at"]:
                seen[key] = o
        before = len(obs)
        self._observations[user_id] = list(seen.values())
        return before - len(self._observations[user_id])

    async def save_to_db(self, user_id: str, project_id: str) -> int:
        """Persist observations to PostgreSQL. Falls back gracefully."""
        try:
            from plotlot.storage.db import get_session
            from sqlalchemy import text
            count = 0
            async with get_session() as session:
                for obs in self._observations.get(user_id, []):
                    await session.execute(
                        text("INSERT INTO harness_memory (user_id, project_id, key, value, source, created_at) VALUES (:uid, :pid, :k, :v, :src, NOW()) ON CONFLICT (user_id, key) DO UPDATE SET value = :v, source = :src, created_at = NOW()"),
                        {"uid": user_id, "pid": project_id or "", "k": obs["key"], "v": str(obs["value"])[:1000], "src": obs.get("source", "unknown")},
                    )
                    count += 1
                await session.commit()
            return count
        except Exception:
            return 0

    async def load_from_db(self, user_id: str, project_id: str) -> int:
        """Load observations from PostgreSQL. Returns count of loaded rows."""
        try:
            from plotlot.storage.db import get_session
            from sqlalchemy import text
            async with get_session() as session:
                result = await session.execute(
                    text("SELECT key, value, source, created_at FROM harness_memory WHERE user_id = :uid AND (project_id = :pid OR project_id = '') ORDER BY created_at DESC LIMIT 100"),
                    {"uid": user_id, "pid": project_id or ""},
                )
                rows = result.fetchall()
                for row in rows:
                    self._observations[user_id].append({"key": row[0], "value": row[1], "source": row[2], "at": str(row[3])})
                return len(rows)
        except Exception:
            return 0

    def _namespace(self, tier: MemoryTier, user_id: str | None, project_id: str | None) -> str:
        uid = user_id or "_global"
        pid = project_id or "_global"
        return f"{tier.value}:{uid}:{pid}"


class MemoryMiddleware(AgentMiddleware):
    """Load memory at agent start, save decisions at agent end."""

    def __init__(self, store: MemoryStore | None = None, user_id: str | None = None, project_id: str | None = None):
        self._store = store or MemoryStore()
        self._user_id = user_id
        self._project_id = project_id

    @property
    def name(self) -> str:
        return "MemoryMiddleware"

    async def before_agent(self, state: AgentState) -> AgentState:
        entries = self._store.retrieve(MemoryTier.SHORT_TERM, self._user_id, self._project_id)
        if entries:
            context = "## Project Memory\n\n"
            for e in entries[:5]:
                context += f"- {e.key}: {str(e.value)[:200]}\n"
            state.add_message("system", context)
        state.custom["memory_loaded"] = len(entries)
        return state

    async def after_agent(self, state: AgentState) -> AgentState:
        for msg in state.messages:
            if msg.get("role") == "assistant" and len(msg.get("content", "")) > 50:
                self._store.store(MemoryEntry(key="last_analysis", value=msg["content"][:500], tier=MemoryTier.SHORT_TERM, user_id=self._user_id, project_id=self._project_id, source="agent_output"))
                break
        return state