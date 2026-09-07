from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DurableRecord:
    tenant_id: str
    kind: str
    record_id: str


@dataclass(frozen=True, slots=True)
class InvalidBundleError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def validate_bundle(records: tuple[DurableRecord, ...]) -> str:
    if not records:
        raise InvalidBundleError("durable bundle cannot be empty")
    tenants = {record.tenant_id for record in records}
    if len(tenants) != 1:
        raise InvalidBundleError("durable bundle must have one tenant")
    kinds = {record.kind for record in records}
    required = {"event", "raw_snapshot", "host_engine_link", "report"}
    if not required.issubset(kinds):
        raise InvalidBundleError("durable bundle is incomplete")
    return records[0].tenant_id
