from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import anyio
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from plotlot.storage.object_snapshots import (
    ObjectConflictError,
    ObjectTamperedError,
    SnapshotMetadata,
    SnapshotReceipt,
)
from plotlot.storage.s3_types import (
    ObjectLegalHoldError,
    S3ObjectStoreConfig,
    decode_metadata,
    encode_snapshot_metadata,
    logical_key,
    physical_key,
    required_string,
)


class S3ImmutableObjectStore:
    physical_key = staticmethod(physical_key)
    logical_key = staticmethod(logical_key)
    decode_metadata = staticmethod(decode_metadata)

    def __init__(self, config: S3ObjectStoreConfig) -> None:
        config.validate()
        self.config = config
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"mode": "standard", "max_attempts": 3},
                s3={"addressing_style": "path"},
            ),
        )

    @property
    def client(self):
        return self._client

    async def initialize(self) -> None:
        await anyio.to_thread.run_sync(self._initialize_sync)

    def _initialize_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.config.bucket)
        except ClientError as error:
            if self._error_code(error) not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self._client.create_bucket(
                Bucket=self.config.bucket,
                ObjectLockEnabledForBucket=True,
            )
        self._client.put_bucket_versioning(
            Bucket=self.config.bucket,
            VersioningConfiguration={"Status": "Enabled"},
        )
        lock = self._client.get_object_lock_configuration(Bucket=self.config.bucket)
        configuration = lock.get("ObjectLockConfiguration", {})
        if configuration.get("ObjectLockEnabled") != "Enabled":
            raise RuntimeError("object-store bucket must have Object Lock enabled")

    async def put_immutable(
        self,
        metadata: SnapshotMetadata,
        content: bytes,
        operation_id: str = "",
    ) -> SnapshotReceipt:
        return await anyio.to_thread.run_sync(
            self._put_immutable_sync,
            metadata,
            bytes(content),
            operation_id,
        )

    def _put_immutable_sync(
        self,
        metadata: SnapshotMetadata,
        content: bytes,
        operation_id: str,
    ) -> SnapshotReceipt:
        object_storage_key = physical_key(metadata.tenant_id, metadata.object_key)
        try:
            self._client.head_object(Bucket=self.config.bucket, Key=object_storage_key)
        except ClientError as error:
            if self._error_code(error) not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            raise ObjectConflictError(metadata.tenant_id, metadata.object_key)

        digest = sha256(content).hexdigest()
        request = {
            "Bucket": self.config.bucket,
            "Key": object_storage_key,
            "Body": content,
            "ContentLength": len(content),
            "ContentType": "application/octet-stream",
            "IfNoneMatch": "*",
            "Metadata": encode_snapshot_metadata(metadata, digest, operation_id),
            "ObjectLockLegalHoldStatus": "ON" if metadata.legal_hold else "OFF",
        }
        now = datetime.now(UTC)
        if metadata.retain_until is not None and metadata.retain_until > now:
            request["ObjectLockMode"] = "GOVERNANCE"
            request["ObjectLockRetainUntilDate"] = metadata.retain_until
        if self.config.sse_kms_key_id is not None:
            request["ServerSideEncryption"] = "aws:kms"
            request["SSEKMSKeyId"] = self.config.sse_kms_key_id
        try:
            response = self._client.put_object(**request)
        except ClientError as error:
            if self._error_code(error) in {"PreconditionFailed", "412"}:
                raise ObjectConflictError(metadata.tenant_id, metadata.object_key) from error
            raise
        version_id = required_string(response, "VersionId")
        return SnapshotReceipt(
            tenant_id=metadata.tenant_id,
            object_key=metadata.object_key,
            source_uri=metadata.source_uri,
            fetched_at=metadata.fetched_at,
            encryption_key_id=metadata.encryption_key_id,
            content_sha256=digest,
            byte_length=len(content),
            version_id=version_id,
            physical_key=object_storage_key,
            retain_until=metadata.retain_until,
            legal_hold=metadata.legal_hold,
            operation_id=operation_id,
        )

    async def get_verified(self, receipt: SnapshotReceipt) -> bytes:
        return await anyio.to_thread.run_sync(self._get_verified_sync, receipt)

    def _get_verified_sync(self, receipt: SnapshotReceipt) -> bytes:
        response = self._client.get_object(
            Bucket=self.config.bucket,
            Key=self._receipt_key(receipt),
            VersionId=receipt.version_id,
        )
        body = response["Body"]
        try:
            content = body.read()
        finally:
            body.close()
        metadata = response.get("Metadata", {})
        expected = encode_snapshot_metadata(
            SnapshotMetadata(
                tenant_id=receipt.tenant_id,
                object_key=receipt.object_key,
                source_uri=receipt.source_uri,
                fetched_at=receipt.fetched_at,
                encryption_key_id=receipt.encryption_key_id,
            ),
            receipt.content_sha256,
            receipt.operation_id,
        )
        content_digest = sha256(content).hexdigest()
        if content_digest != receipt.content_sha256 or any(
            metadata.get(key) != value for key, value in expected.items()
        ):
            raise ObjectTamperedError(receipt.tenant_id, receipt.object_key)
        return bytes(content)

    async def version_exists(self, receipt: SnapshotReceipt) -> bool:
        return await anyio.to_thread.run_sync(self._version_exists_sync, receipt)

    def _version_exists_sync(self, receipt: SnapshotReceipt) -> bool:
        try:
            self._client.head_object(
                Bucket=self.config.bucket,
                Key=self._receipt_key(receipt),
                VersionId=receipt.version_id,
            )
        except ClientError as error:
            if self._error_code(error) in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}:
                return False
            raise
        return True

    async def is_legal_hold_enabled(self, receipt: SnapshotReceipt) -> bool:
        return await anyio.to_thread.run_sync(self._is_legal_hold_enabled_sync, receipt)

    def _is_legal_hold_enabled_sync(self, receipt: SnapshotReceipt) -> bool:
        response = self._client.get_object_legal_hold(
            Bucket=self.config.bucket,
            Key=self._receipt_key(receipt),
            VersionId=receipt.version_id,
        )
        legal_hold = response.get("LegalHold", {})
        status = legal_hold.get("Status")
        return isinstance(status, str) and status == "ON"

    async def delete_version(self, receipt: SnapshotReceipt) -> None:
        await anyio.to_thread.run_sync(self._delete_version_sync, receipt)

    def _delete_version_sync(self, receipt: SnapshotReceipt) -> None:
        if not self._version_exists_sync(receipt):
            return
        if self._is_legal_hold_enabled_sync(receipt):
            raise ObjectLegalHoldError(
                receipt.tenant_id,
                receipt.object_key,
                receipt.version_id,
            )
        self._client.delete_object(
            Bucket=self.config.bucket,
            Key=self._receipt_key(receipt),
            VersionId=receipt.version_id,
        )

    async def set_legal_hold(self, receipt: SnapshotReceipt, enabled: bool) -> None:
        await anyio.to_thread.run_sync(self._set_legal_hold_sync, receipt, enabled)

    def _set_legal_hold_sync(self, receipt: SnapshotReceipt, enabled: bool) -> None:
        self._client.put_object_legal_hold(
            Bucket=self.config.bucket,
            Key=self._receipt_key(receipt),
            VersionId=receipt.version_id,
            LegalHold={"Status": "ON" if enabled else "OFF"},
        )

    def _receipt_key(self, receipt: SnapshotReceipt) -> str:
        expected = physical_key(receipt.tenant_id, receipt.object_key)
        if receipt.physical_key and receipt.physical_key != expected:
            raise ObjectTamperedError(receipt.tenant_id, receipt.object_key)
        return expected

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))
