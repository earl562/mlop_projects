from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from plotlot.storage.s3_objects import S3ImmutableObjectStore
from plotlot.storage.s3_types import (
    ObjectVersionPayload,
    S3ObjectStoreConfig,
    decode_metadata,
    logical_key,
)
from plotlot.storage.s3_versions import S3VersionArchive


@dataclass(frozen=True, slots=True)
class ArchiveReceipt:
    version_count: int
    manifest_sha256: str


class ObjectArchiveService:
    def __init__(self, object_store: S3ImmutableObjectStore) -> None:
        self._object_store = object_store
        self._versions = S3VersionArchive(object_store)

    async def export(self, archive_path: Path) -> ArchiveReceipt:
        records = await self._versions.list_version_records()
        versions: list[ObjectVersionPayload] = []
        for record in records:
            physical_key = record.get("Key")
            version_id = record.get("VersionId")
            if not isinstance(physical_key, str) or not isinstance(version_id, str):
                raise RuntimeError("version listing omitted key or version id")
            versions.append(await self._versions.export_version(physical_key, version_id))
        versions.sort(key=lambda item: (item.last_modified, item.physical_key, item.version_id))

        entries: list[dict[str, object]] = []
        payloads: list[tuple[str, bytes]] = []
        for index, version in enumerate(versions):
            member = f"objects/{index:08d}.bin"
            payloads.append((member, version.content))
            entries.append(
                {
                    "physical_key": version.physical_key,
                    "version_id": version.version_id,
                    "member": member,
                    "content_sha256": sha256(version.content).hexdigest(),
                    "byte_length": len(version.content),
                    "metadata": version.metadata,
                    "content_type": version.content_type,
                    "legal_hold": version.legal_hold,
                    "retention_mode": version.retention_mode,
                    "retain_until": (
                        version.retain_until.isoformat()
                        if version.retain_until is not None
                        else None
                    ),
                    "last_modified": version.last_modified.isoformat(),
                }
            )
        manifest = {
            "schema": "PlotLotObjectArchiveV2",
            "bucket": self._object_store.config.bucket,
            "versions": entries,
        }
        manifest_bytes = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w") as archive:
            self._add_bytes(archive, "manifest.json", manifest_bytes)
            for member, content in payloads:
                self._add_bytes(archive, member, content)
        return ArchiveReceipt(
            version_count=len(versions),
            manifest_sha256=sha256(manifest_bytes).hexdigest(),
        )

    async def restore(self, archive_path: Path) -> list[dict[str, str]]:
        payloads = self.validate(archive_path)
        version_map: list[dict[str, str]] = []
        for payload in payloads:
            destination_version = await self._versions.restore_version(payload)
            version_map.append(
                {
                    "physical_key": payload.physical_key,
                    "source_version_id": payload.version_id,
                    "destination_version_id": destination_version,
                }
            )
        return version_map

    def validate(self, archive_path: Path) -> list[ObjectVersionPayload]:
        with tarfile.open(archive_path, "r") as archive:
            manifest_member = archive.getmember("manifest.json")
            manifest_file = archive.extractfile(manifest_member)
            if manifest_file is None:
                raise RuntimeError("object archive has no manifest")
            manifest = json.loads(manifest_file.read())
            if manifest.get("schema") != "PlotLotObjectArchiveV2":
                raise RuntimeError("unsupported object archive schema")
            entries = manifest.get("versions")
            if not isinstance(entries, list):
                raise RuntimeError("object archive versions must be a list")
            payloads: list[ObjectVersionPayload] = []
            identities: set[tuple[str, str]] = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise RuntimeError("object archive entry must be an object")
                payload = self._payload_from_archive(archive, entry)
                identity = (payload.physical_key, payload.version_id)
                if identity in identities:
                    raise RuntimeError("duplicate object archive version identity")
                identities.add(identity)
                payloads.append(payload)
        return payloads

    def _payload_from_archive(
        self,
        archive: tarfile.TarFile,
        entry: dict[str, object],
    ) -> ObjectVersionPayload:
        physical_key = self._required_string(entry, "physical_key")
        source_version = self._required_string(entry, "version_id")
        member_name = self._required_string(entry, "member")
        if not member_name.startswith("objects/") or "/" in member_name.removeprefix("objects/"):
            raise RuntimeError("unsafe object archive member")
        member = archive.getmember(member_name)
        member_file = archive.extractfile(member)
        if member_file is None:
            raise RuntimeError("object archive payload is missing")
        content = member_file.read()
        expected_digest = self._required_string(entry, "content_sha256")
        if sha256(content).hexdigest() != expected_digest:
            raise RuntimeError("object archive payload hash mismatch")
        byte_length = entry.get("byte_length")
        if not isinstance(byte_length, int) or byte_length != len(content):
            raise RuntimeError("object archive payload length mismatch")
        metadata = entry.get("metadata")
        if not isinstance(metadata, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
        ):
            raise RuntimeError("object archive metadata is invalid")
        tenant_id, object_key = logical_key(physical_key)
        decoded = decode_metadata(metadata)
        if decoded.get("tenant-id") != tenant_id or decoded.get("object-key") != object_key:
            raise RuntimeError("object archive tenant metadata mismatch")
        retain_value = entry.get("retain_until")
        retain_until = (
            datetime.fromisoformat(retain_value) if isinstance(retain_value, str) else None
        )
        return ObjectVersionPayload(
            physical_key=physical_key,
            version_id=source_version,
            content=content,
            metadata=metadata,
            content_type=self._required_string(entry, "content_type"),
            legal_hold=entry.get("legal_hold") is True,
            retention_mode=(
                self._required_string(entry, "retention_mode")
                if entry.get("retention_mode") is not None
                else None
            ),
            retain_until=retain_until,
            last_modified=datetime.fromisoformat(self._required_string(entry, "last_modified")),
        )

    @staticmethod
    def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        info.mode = 0o600
        info.mtime = 0
        archive.addfile(info, io.BytesIO(content))

    @staticmethod
    def _required_string(source: dict[str, object], key: str) -> str:
        value = source.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"object archive entry missing {key}")
        return value


def _config_from_arguments(arguments: argparse.Namespace) -> S3ObjectStoreConfig:
    return S3ObjectStoreConfig(
        endpoint_url=arguments.endpoint,
        bucket=arguments.bucket,
        access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region=arguments.region,
    )


async def _run(arguments: argparse.Namespace) -> int:
    store = S3ImmutableObjectStore(_config_from_arguments(arguments))
    service = ObjectArchiveService(store)
    if arguments.command == "validate":
        print(json.dumps({"validated_versions": len(service.validate(arguments.archive))}))
        return 0
    await store.initialize()
    if arguments.command == "export":
        receipt = await service.export(arguments.archive)
        print(
            json.dumps(
                {
                    "version_count": receipt.version_count,
                    "manifest_sha256": receipt.manifest_sha256,
                },
                sort_keys=True,
            )
        )
        return 0
    version_map = await service.restore(arguments.archive)
    arguments.version_map.write_text(
        json.dumps(
            {"schema": "PlotLotVersionMapV2", "versions": version_map},
            sort_keys=True,
        )
        + "\n"
    )
    print(json.dumps({"restored_versions": len(version_map)}, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "restore", "validate"):
        child = subparsers.add_parser(command)
        child.add_argument("--endpoint", required=True)
        child.add_argument("--bucket", required=True)
        child.add_argument("--region", default="us-east-1")
        child.add_argument("--archive", required=True, type=Path)
        if command == "restore":
            child.add_argument("--version-map", required=True, type=Path)
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parser().parse_args())))


if __name__ == "__main__":
    main()
