from __future__ import annotations

from datetime import UTC, datetime

import anyio
from botocore.exceptions import ClientError

from plotlot.storage.s3_objects import S3ImmutableObjectStore
from plotlot.storage.s3_types import ObjectVersionPayload, required_string


class S3VersionArchive:
    def __init__(self, object_store: S3ImmutableObjectStore) -> None:
        self._store = object_store
        self._client = object_store.client

    async def list_version_records(self) -> list[dict[str, object]]:
        return await anyio.to_thread.run_sync(self._list_version_records_sync)

    def _list_version_records_sync(self) -> list[dict[str, object]]:
        paginator = self._client.get_paginator("list_object_versions")
        records: list[dict[str, object]] = []
        for page in paginator.paginate(Bucket=self._store.config.bucket):
            for item in page.get("Versions", []):
                records.append(dict(item))
        return records

    async def export_version(
        self,
        physical_key: str,
        version_id: str,
    ) -> ObjectVersionPayload:
        return await anyio.to_thread.run_sync(
            self._export_version_sync,
            physical_key,
            version_id,
        )

    def _export_version_sync(
        self,
        physical_key: str,
        version_id: str,
    ) -> ObjectVersionPayload:
        response = self._client.get_object(
            Bucket=self._store.config.bucket,
            Key=physical_key,
            VersionId=version_id,
        )
        body = response["Body"]
        try:
            content = body.read()
        finally:
            body.close()
        hold_response = self._client.get_object_legal_hold(
            Bucket=self._store.config.bucket,
            Key=physical_key,
            VersionId=version_id,
        )
        hold_status = hold_response.get("LegalHold", {}).get("Status")
        legal_hold = isinstance(hold_status, str) and hold_status == "ON"
        retain_until = None
        retention_mode = None
        try:
            retention = self._client.get_object_retention(
                Bucket=self._store.config.bucket,
                Key=physical_key,
                VersionId=version_id,
            )
        except ClientError as error:
            if self._error_code(error) not in {"InvalidRequest", "NoSuchKey", "NotFound"}:
                raise
        else:
            retention_fields = retention.get("Retention", {})
            value = retention_fields.get("RetainUntilDate")
            if isinstance(value, datetime):
                retain_until = value
            mode = retention_fields.get("Mode")
            if isinstance(mode, str):
                retention_mode = mode
        last_modified = response.get("LastModified")
        if not isinstance(last_modified, datetime):
            raise RuntimeError("object version is missing LastModified")
        return ObjectVersionPayload(
            physical_key=physical_key,
            version_id=version_id,
            content=bytes(content),
            metadata=dict(response.get("Metadata", {})),
            content_type=str(response.get("ContentType", "application/octet-stream")),
            legal_hold=legal_hold,
            retention_mode=retention_mode,
            retain_until=retain_until,
            last_modified=last_modified,
        )

    async def restore_version(self, payload: ObjectVersionPayload) -> str:
        return await anyio.to_thread.run_sync(self._restore_version_sync, payload)

    def _restore_version_sync(self, payload: ObjectVersionPayload) -> str:
        request = {
            "Bucket": self._store.config.bucket,
            "Key": payload.physical_key,
            "Body": payload.content,
            "ContentLength": len(payload.content),
            "ContentType": payload.content_type,
            "Metadata": payload.metadata,
            "ObjectLockLegalHoldStatus": "ON" if payload.legal_hold else "OFF",
        }
        if payload.retain_until is not None and payload.retain_until > datetime.now(UTC):
            request["ObjectLockMode"] = payload.retention_mode or "GOVERNANCE"
            request["ObjectLockRetainUntilDate"] = payload.retain_until
        response = self._client.put_object(**request)
        return required_string(response, "VersionId")

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))
