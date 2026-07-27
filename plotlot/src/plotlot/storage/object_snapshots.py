from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    tenant_id: str
    object_key: str
    source_uri: str
    fetched_at: datetime
    encryption_key_id: str


@dataclass(frozen=True, slots=True)
class SnapshotReceipt:
    tenant_id: str
    object_key: str
    source_uri: str
    fetched_at: datetime
    encryption_key_id: str
    content_sha256: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class ObjectConflictError(Exception):
    tenant_id: str
    object_key: str

    def __str__(self) -> str:
        return f"immutable object already exists: {self.tenant_id}/{self.object_key}"


@dataclass(frozen=True, slots=True)
class ObjectTamperedError(Exception):
    tenant_id: str
    object_key: str

    def __str__(self) -> str:
        return f"object hash mismatch: {self.tenant_id}/{self.object_key}"


class ImmutableMemoryObjectStore:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put_immutable(self, metadata: SnapshotMetadata, content: bytes) -> SnapshotReceipt:
        key = (metadata.tenant_id, metadata.object_key)
        if key in self._objects:
            raise ObjectConflictError(*key)
        self._objects[key] = bytes(content)
        return SnapshotReceipt(
            tenant_id=metadata.tenant_id,
            object_key=metadata.object_key,
            source_uri=metadata.source_uri,
            fetched_at=metadata.fetched_at,
            encryption_key_id=metadata.encryption_key_id,
            content_sha256=sha256(content).hexdigest(),
            byte_length=len(content),
        )

    def get_verified(self, receipt: SnapshotReceipt) -> bytes:
        content = self._objects[(receipt.tenant_id, receipt.object_key)]
        if sha256(content).hexdigest() != receipt.content_sha256:
            raise ObjectTamperedError(receipt.tenant_id, receipt.object_key)
        return bytes(content)

    def inject_tamper_for_test(self, tenant_id: str, object_key: str, content: bytes) -> None:
        self._objects[(tenant_id, object_key)] = bytes(content)
