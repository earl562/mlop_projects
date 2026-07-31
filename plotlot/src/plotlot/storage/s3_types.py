from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, unquote

from plotlot.storage.object_snapshots import SnapshotMetadata


_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")


@dataclass(frozen=True, slots=True)
class S3ObjectStoreConfig:
    endpoint_url: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str
    sse_kms_key_id: str | None = None

    def validate(self) -> None:
        if not self.endpoint_url.startswith(("http://", "https://")):
            raise ValueError("object-store endpoint must use http or https")
        if not self.bucket or not self.access_key_id or not self.secret_access_key:
            raise ValueError("object-store bucket and explicit credentials are required")


@dataclass(frozen=True, slots=True)
class ObjectLegalHoldError(Exception):
    tenant_id: str
    object_key: str
    version_id: str

    def __str__(self) -> str:
        return f"object legal hold prevents deletion: {self.tenant_id}/{self.object_key}"


@dataclass(frozen=True, slots=True)
class ObjectVersionPayload:
    physical_key: str
    version_id: str
    content: bytes
    metadata: dict[str, str]
    content_type: str
    legal_hold: bool
    retention_mode: str | None
    retain_until: datetime | None
    last_modified: datetime


def physical_key(tenant_id: str, object_key: str) -> str:
    if not _KEY_PATTERN.fullmatch(tenant_id):
        raise ValueError("invalid tenant object-store key")
    if (
        not _KEY_PATTERN.fullmatch(object_key)
        or object_key.startswith("/")
        or "//" in object_key
        or ".." in object_key.split("/")
    ):
        raise ValueError("invalid object-store key")
    return f"tenants/{tenant_id}/{object_key}"


def logical_key(value: str) -> tuple[str, str]:
    parts = value.split("/", 2)
    if len(parts) != 3 or parts[0] != "tenants":
        raise ValueError("object is outside tenant namespace")
    return parts[1], parts[2]


def encode_snapshot_metadata(
    metadata: SnapshotMetadata,
    digest: str,
    operation_id: str = "",
) -> dict[str, str]:
    encoded = {
        "tenant-id": quote(metadata.tenant_id, safe=""),
        "object-key": quote(metadata.object_key, safe=""),
        "source-uri": quote(metadata.source_uri, safe=""),
        "fetched-at": quote(metadata.fetched_at.astimezone(UTC).isoformat(), safe=""),
        "encryption-key-id": quote(metadata.encryption_key_id, safe=""),
        "content-sha256": digest,
    }
    if operation_id:
        encoded["operation-id"] = quote(operation_id, safe="")
    return encoded


def decode_metadata(metadata: dict[str, str]) -> dict[str, str]:
    return {key: unquote(value) for key, value in metadata.items()}


def required_string(response: dict[str, object], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"object-store response missing {key}")
    return value
