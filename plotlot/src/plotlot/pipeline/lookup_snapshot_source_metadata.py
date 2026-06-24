from __future__ import annotations

import re
from typing import Final

from plotlot.core.lookup_snapshot import EvidenceId, EvidenceSourceMetadata
from plotlot.core.types import ZoningReport

_SOURCE_URL_RE: Final = re.compile(r"https?://[^\s)>\]]+")


def build_source_metadata(
    report: ZoningReport,
    ordinance_evidence_ids: tuple[EvidenceId, ...],
) -> tuple[EvidenceSourceMetadata, ...]:
    metadata: list[EvidenceSourceMetadata] = []
    for index, evidence_id in enumerate(ordinance_evidence_ids):
        ref = report.source_refs[index]
        metadata.append(
            EvidenceSourceMetadata(
                evidence_id=evidence_id,
                source_url=_source_url_at(report.sources, index),
                source_title=ref.section_title or ref.section or str(evidence_id),
            )
        )
    return tuple(metadata)


def _source_url_at(sources: list[str], index: int) -> str:
    if index >= len(sources):
        return ""
    match = _SOURCE_URL_RE.search(sources[index])
    if match is None:
        return ""
    return match.group(0).rstrip(".,;")
