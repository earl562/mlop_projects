from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from plotlot.comps.dates import evidence_date_sort_key
from plotlot.comps.models import SaleEvidence
from plotlot.comps.qualification_rules import CandidateAssessment, _normalized_identity

_SOURCE_PRIORITY: Final = {"county": 0, "recorder": 1, "user_reviewed": 2}


@dataclass(frozen=True, slots=True)
class TransactionIdentity:
    kind: str
    state: str
    county: str
    parcel_id: str
    namespace: str
    value: str


def _transaction_identities(candidate: SaleEvidence) -> tuple[TransactionIdentity, ...]:
    if not candidate.parcel_id.strip():
        return ()
    common = (
        candidate.state.strip().casefold(),
        candidate.county.strip().casefold(),
        _normalized_identity(candidate.parcel_id),
    )
    identities: list[TransactionIdentity] = []
    if candidate.recorded_document.strip():
        identities.append(
            TransactionIdentity(
                "recorded_document",
                *common,
                "",
                _normalized_identity(candidate.recorded_document),
            )
        )
    if candidate.source_record_id.strip():
        namespace = f"{candidate.source_kind}:{candidate.source_url.strip()}"
        identities.append(
            TransactionIdentity(
                "source_record_id",
                *common,
                namespace,
                _normalized_identity(candidate.source_record_id),
            )
        )
    return tuple(identities)


def _root(parents: list[int], index: int) -> int:
    while parents[index] != index:
        parents[index] = parents[parents[index]]
        index = parents[index]
    return index


def _union(parents: list[int], left: int, right: int) -> None:
    left_root = _root(parents, left)
    right_root = _root(parents, right)
    if left_root != right_root:
        parents[right_root] = left_root


def _transaction_groups(candidates: Sequence[SaleEvidence]) -> tuple[tuple[int, ...], ...]:
    parents = list(range(len(candidates)))
    owners: dict[TransactionIdentity, int] = {}
    participating: set[int] = set()
    for index, candidate in enumerate(candidates):
        for identity in _transaction_identities(candidate):
            participating.add(index)
            owner = owners.setdefault(identity, index)
            _union(parents, index, owner)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in participating:
        groups[_root(parents, index)].append(index)
    return tuple(tuple(indices) for indices in groups.values() if len(indices) > 1)


def block_duplicate_transactions(
    candidates: Sequence[SaleEvidence], assessments: Sequence[CandidateAssessment]
) -> tuple[CandidateAssessment, ...]:
    updated = list(assessments)
    for indices in _transaction_groups(candidates):
        facts = {
            (
                candidates[index].sale_price,
                candidates[index].sale_date,
                candidates[index].date_precision,
                candidates[index].category,
                candidates[index].property_type,
            )
            for index in indices
        }
        if len(facts) > 1:
            for index in indices:
                updated[index] = replace(
                    updated[index],
                    reasons=(*updated[index].reasons, "conflicting_transaction_evidence"),
                )
            continue
        keeper = min(
            indices,
            key=lambda index: (
                _SOURCE_PRIORITY.get(candidates[index].source_kind, 99),
                candidates[index].evidence_id,
            ),
        )
        for index in indices:
            if index != keeper:
                updated[index] = replace(
                    updated[index], reasons=(*updated[index].reasons, "duplicate_transaction")
                )
    return tuple(updated)


def block_duplicate_evidence_ids(
    candidates: Sequence[SaleEvidence], assessments: Sequence[CandidateAssessment]
) -> tuple[CandidateAssessment, ...]:
    updated = list(assessments)
    groups: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        groups[candidate.evidence_id.strip().casefold()].append(index)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        for index in indices:
            updated[index] = replace(
                updated[index], reasons=(*updated[index].reasons, "duplicate_evidence_id")
            )
    return tuple(updated)


def limit_one_sale_per_parcel(
    candidates: Sequence[SaleEvidence], assessments: Sequence[CandidateAssessment]
) -> tuple[CandidateAssessment, ...]:
    updated = list(assessments)
    groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    for index, (candidate, assessment) in enumerate(zip(candidates, assessments, strict=True)):
        if not assessment.reasons:
            groups[
                (
                    candidate.state.strip().casefold(),
                    candidate.county.strip().casefold(),
                    _normalized_identity(candidate.parcel_id),
                    candidate.category,
                )
            ].append(index)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        keeper = max(
            indices,
            key=lambda index: (
                evidence_date_sort_key(
                    candidates[index].sale_date, candidates[index].date_precision
                ),
                candidates[index].evidence_id,
            ),
        )
        for index in indices:
            if index != keeper:
                updated[index] = replace(updated[index], reasons=("not_selected",))
    return tuple(updated)
