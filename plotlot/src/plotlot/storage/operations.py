from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from plotlot.storage.object_snapshots import SnapshotMetadata, SnapshotReceipt


def operation_id(kind: str, idempotency_key: str) -> str:
    return f"{kind.lower()}-{sha256(idempotency_key.encode()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class StorageOperation:
    tenant_id: str
    operation_id: str
    operation_type: str
    status: str
    object_key: str
    snapshot_id: str
    content_sha256: str
    byte_length: int
    source_uri: str
    fetched_at: datetime
    encryption_algorithm: str
    encryption_key_id: str
    retain_until: datetime
    legal_hold: bool
    object_version_id: str | None
    request_id: str | None
    requested_by: str
    requested_at: datetime

    def metadata(self) -> SnapshotMetadata:
        return SnapshotMetadata(
            tenant_id=self.tenant_id,
            object_key=self.object_key,
            source_uri=self.source_uri,
            fetched_at=self.fetched_at,
            encryption_key_id=self.encryption_key_id,
            retain_until=self.retain_until,
            legal_hold=self.legal_hold,
        )

    def receipt(self) -> SnapshotReceipt:
        if self.object_version_id is None:
            raise RuntimeError("storage operation has no object version")
        return SnapshotReceipt(
            tenant_id=self.tenant_id,
            object_key=self.object_key,
            source_uri=self.source_uri,
            fetched_at=self.fetched_at,
            encryption_key_id=self.encryption_key_id,
            content_sha256=self.content_sha256,
            byte_length=self.byte_length,
            version_id=self.object_version_id,
            physical_key=f"tenants/{self.tenant_id}/{self.object_key}",
            retain_until=self.retain_until,
            legal_hold=self.legal_hold,
            operation_id=self.operation_id,
        )
