from __future__ import annotations

from hashlib import sha256

import anyio

from plotlot.storage.object_snapshots import (
    ObjectConflictError,
    SnapshotMetadata,
    SnapshotReceipt,
)
from plotlot.storage.s3_objects import S3ImmutableObjectStore
from plotlot.storage.s3_types import encode_snapshot_metadata, physical_key


class S3OperationWriter:
    def __init__(self, object_store: S3ImmutableObjectStore) -> None:
        self._store = object_store
        self._client = object_store.client

    async def put_or_adopt(
        self,
        operation_id: str,
        metadata: SnapshotMetadata,
        content: bytes,
    ) -> SnapshotReceipt:
        digest = sha256(content).hexdigest()
        existing = await self.adopt_existing(
            operation_id,
            metadata,
            digest,
            len(content),
        )
        if existing is not None:
            return existing
        try:
            return await self._store.put_immutable(metadata, content, operation_id)
        except ObjectConflictError:
            existing = await self.adopt_existing(
                operation_id,
                metadata,
                digest,
                len(content),
            )
            if existing is None:
                raise
            return existing

    async def adopt_existing(
        self,
        operation_id: str,
        metadata: SnapshotMetadata,
        digest: str,
        byte_length: int,
    ) -> SnapshotReceipt | None:
        return await anyio.to_thread.run_sync(
            self._adopt_existing_sync,
            operation_id,
            metadata,
            digest,
            byte_length,
        )

    def _adopt_existing_sync(
        self,
        operation_id: str,
        metadata: SnapshotMetadata,
        digest: str,
        byte_length: int,
    ) -> SnapshotReceipt | None:
        key = physical_key(metadata.tenant_id, metadata.object_key)
        expected = encode_snapshot_metadata(metadata, digest, operation_id)
        matching_versions: list[str] = []
        paginator = self._client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=self._store.config.bucket, Prefix=key):
            for listed in page.get("Versions", []):
                if listed.get("Key") != key or not isinstance(listed.get("VersionId"), str):
                    continue
                version_id = listed["VersionId"]
                response = self._client.head_object(
                    Bucket=self._store.config.bucket,
                    Key=key,
                    VersionId=version_id,
                )
                stored_metadata = response.get("Metadata", {})
                if response.get("ContentLength") == byte_length and all(
                    stored_metadata.get(name) == value for name, value in expected.items()
                ):
                    matching_versions.append(version_id)
        if not matching_versions:
            return None
        if len(matching_versions) != 1:
            raise RuntimeError("storage operation owns multiple object versions")
        return SnapshotReceipt(
            tenant_id=metadata.tenant_id,
            object_key=metadata.object_key,
            source_uri=metadata.source_uri,
            fetched_at=metadata.fetched_at,
            encryption_key_id=metadata.encryption_key_id,
            content_sha256=digest,
            byte_length=byte_length,
            version_id=matching_versions[0],
            physical_key=key,
            retain_until=metadata.retain_until,
            legal_hold=metadata.legal_hold,
            operation_id=operation_id,
        )
