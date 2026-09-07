"""Ingestion pipeline — snapshot → parse → chunks → events → quality (Phase 5).

Master spec §5 + §6 + §7. Wires the Phase 3 snapshot service + Phase 4 table
parser into one run per JurisdictionSourceAuthority. Produces chunks that link
to (source_authority_id, snapshot_id) with chunk_kind set, emits the full event
sequence, and computes a coverage quality score. Idempotent on unchanged source.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from bs4 import BeautifulSoup

from plotlot.ingestion.events import HarnessEvent, IngestionEventType
from plotlot.ingestion.parsing.tables import (
    ParsedTable,
    TableKind,
    classify_table,
    parse_html_table,
)
from plotlot.ingestion.snapshot_service import fetch_and_snapshot
from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot
from plotlot.ingestion.source_authorities.models import JurisdictionSourceAuthority

Fetcher = Callable[[str], Awaitable[tuple[int, str]]]


@dataclass
class IngestedChunk:
    """A chunk produced by ingestion, linked to its authority + snapshot."""

    id: str
    text: str
    chunk_kind: str
    source_authority_id: str
    snapshot_id: str
    section_heading: str = ""
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class IngestionResult:
    snapshot: OrdinanceSourceSnapshot | None
    chunks: list[IngestedChunk]
    events: list[HarnessEvent]
    changed: bool
    quality_score: float | None = None


_MAX_CHUNK_CHARS = 1500


async def run_ingestion(
    *,
    authority: JurisdictionSourceAuthority,
    fetcher: Fetcher,
    prior_snapshot: OrdinanceSourceSnapshot | None,
) -> IngestionResult:
    """Run the full ingestion pipeline for one authority.

    1. fetch + snapshot (Phase 3) — detects change.
    2. parse HTML → sections + tables (Phase 4) — chunk_kind classification.
    3. emit chunk_created events; chunks link to authority + snapshot.
    4. compute coverage quality score; emit jurisdiction_quality_scored.
    """
    snap_result = await fetch_and_snapshot(
        source_authority_id=authority.id,
        source_url=authority.source_url,
        fetcher=fetcher,
        prior_snapshot=prior_snapshot,
    )
    events: list[HarnessEvent] = [snap_result.event]

    # Unchanged / failed → no parsing.
    if snap_result.snapshot is None or not snap_result.changed:
        return IngestionResult(
            snapshot=snap_result.snapshot,
            chunks=[],
            events=events,
            changed=snap_result.changed,
        )

    snapshot = snap_result.snapshot
    events.append(
        HarnessEvent(
            type=IngestionEventType.PARSER_STARTED,
            severity="debug",
            payload={
                "authority_id": authority.id,
                "snapshot_id": snapshot.content_hash[:16],
                "parser_version": "phase5-v1",
            },
        )
    )

    chunks = _parse_to_chunks(
        html=snapshot.content,
        authority_id=authority.id,
        snapshot_id=snapshot.content_hash[:16],
        events=events,
    )

    events.append(
        HarnessEvent(
            type=IngestionEventType.PARSER_COMPLETED,
            severity="info",
            payload={
                "authority_id": authority.id,
                "sections": len({c.section_heading for c in chunks}),
                "chunks": len(chunks),
                "tables": sum(1 for c in chunks if c.chunk_kind != "narrative"),
                "warnings": [],
            },
        )
    )

    quality = _compute_quality_score(chunks)
    events.append(
        HarnessEvent(
            type=IngestionEventType.JURISDICTION_QUALITY_SCORED,
            severity="info",
            payload={
                "authority_id": authority.id,
                "coverage_score": quality,
                "dimensions": ["chunk_count", "table_ratio", "dimensional_table_present"],
            },
        )
    )

    return IngestionResult(
        snapshot=snapshot,
        chunks=chunks,
        events=events,
        changed=True,
        quality_score=quality,
    )


def _parse_to_chunks(
    *,
    html: str,
    authority_id: str,
    snapshot_id: str,
    events: list[HarnessEvent],
) -> list[IngestedChunk]:
    """Parse HTML into chunks: each <table> becomes a dimensional/use/etc chunk;
    prose between tables becomes narrative chunks. Preserves header→cell association."""
    soup = BeautifulSoup(html, "html.parser")
    chunks: list[IngestedChunk] = []
    idx = 0

    # Find the first heading as section context.
    first_heading = soup.find(["h1", "h2", "h3", "h4"])
    section_heading = first_heading.get_text(strip=True) if first_heading else "unknown"

    # Tables → typed chunks.
    for table in soup.find_all("table"):
        parsed = parse_html_table(str(table))
        if parsed is None:
            continue
        kind = classify_table(parsed)
        parsed.kind = kind
        # Serialize the table as labeled rows (header preserved, not flattened).
        text = _serialize_table(parsed)
        chunk = IngestedChunk(
            id=f"chunk_{uuid.uuid4().hex[:12]}",
            text=text,
            chunk_kind=kind.value,
            source_authority_id=authority_id,
            snapshot_id=snapshot_id,
            section_heading=section_heading,
            chunk_index=idx,
            metadata={"headers": parsed.headers, "row_count": len(parsed.rows)},
        )
        chunks.append(chunk)
        events.append(
            HarnessEvent(
                type=IngestionEventType.CHUNK_CREATED,
                severity="debug",
                payload={
                    "chunk_id": chunk.id,
                    "section_id": section_heading,
                    "chunk_kind": chunk.chunk_kind,
                    "chunk_index": idx,
                },
            )
        )
        idx += 1

    # Prose (non-table text) → narrative chunks, split to max size.
    for el in soup.find_all(["p", "li"]):
        text = el.get_text(strip=True)
        if not text or len(text) < 40:
            continue
        for piece in _split_text(text, _MAX_CHUNK_CHARS):
            chunk = IngestedChunk(
                id=f"chunk_{uuid.uuid4().hex[:12]}",
                text=piece,
                chunk_kind="narrative",
                source_authority_id=authority_id,
                snapshot_id=snapshot_id,
                section_heading=section_heading,
                chunk_index=idx,
            )
            chunks.append(chunk)
            events.append(
                HarnessEvent(
                    type=IngestionEventType.CHUNK_CREATED,
                    severity="debug",
                    payload={
                        "chunk_id": chunk.id,
                        "section_id": section_heading,
                        "chunk_kind": "narrative",
                        "chunk_index": idx,
                    },
                )
            )
            idx += 1
    return chunks


def _serialize_table(table: ParsedTable) -> str:
    """Emit a table as labeled rows: 'RowLabel — Header: value; Header: value'."""
    lines = [f"Headers: {' | '.join(table.headers)}"]
    for row in table.rows:
        label = row[0] if row else ""
        pairs = [
            f"{table.headers[i]}: {row[i]}"
            for i in range(1, min(len(row), len(table.headers)))
            if row[i]
        ]
        lines.append(f"{label} — {'; '.join(pairs)}" if pairs else label)
    return "\n".join(lines)


def _split_text(text: str, max_size: int) -> list[str]:
    if len(text) <= max_size:
        return [text]
    return [text[i : i + max_size] for i in range(0, len(text), max_size)]


def _compute_quality_score(chunks: list[IngestedChunk]) -> float:
    """Coverage quality: chunk volume + table ratio + dimensional-table presence.

    0.0–1.0. A jurisdiction with dimensional tables + a healthy chunk count
    scores higher than one with only narrative prose.
    """
    if not chunks:
        return 0.0
    table_chunks = [c for c in chunks if c.chunk_kind != "narrative"]
    dimensional_present = any(c.chunk_kind == TableKind.DIMENSIONAL_TABLE.value for c in chunks)
    table_ratio = len(table_chunks) / len(chunks)
    volume_score = min(1.0, len(chunks) / 50.0)  # 50+ chunks = full coverage
    score = 0.4 * volume_score + 0.3 * table_ratio + (0.3 if dimensional_present else 0.0)
    return round(min(1.0, score), 2)


__all__ = ["IngestedChunk", "IngestionResult", "run_ingestion"]
