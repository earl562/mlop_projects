from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "PlotLotBaselineV1"
RECORD_KEYS = {"path", "kind", "mode", "sha256", "size"}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(rb"\bsk-(?:proj-|live_)?[A-Za-z0-9_-]{32,}\b"),
    re.compile(
        rb"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*"
        rb"[\"']?[A-Za-z0-9_./+=-]{32,}"
    ),
)


class BaselineError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative(path: str) -> PurePosixPath:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise BaselineError(f"unsafe relative path: {path!r}")
    if candidate.as_posix() != path:
        raise BaselineError(f"non-canonical path: {path!r}")
    return candidate


def scan_secret_bytes(value: bytes, label: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise BaselineError(f"secret-shaped content rejected in {label}")


def file_record(root: Path, path: str) -> dict[str, object]:
    relative = _safe_relative(path)
    target = root.joinpath(*relative.parts)
    metadata = target.lstat()
    mode = f"{stat.S_IMODE(metadata.st_mode):04o}"
    if stat.S_ISLNK(metadata.st_mode):
        link = os.readlink(target)
        resolved = (target.parent / link).resolve(strict=False)
        try:
            resolved.relative_to(root.resolve())
        except ValueError as error:
            raise BaselineError(f"symlink escapes repository: {path}") from error
        payload = link.encode("utf-8", "surrogateescape")
        kind = "symlink"
    elif stat.S_ISREG(metadata.st_mode):
        payload = target.read_bytes()
        kind = "file"
    else:
        raise BaselineError(f"unsupported file kind: {path}")
    return {
        "path": path,
        "kind": kind,
        "mode": mode,
        "sha256": sha256_bytes(payload),
        "size": len(payload),
    }


def _validate_record_shape(record: object) -> dict[str, object]:
    if not isinstance(record, dict) or set(record) != RECORD_KEYS:
        raise BaselineError("manifest record has invalid keys")
    if not all(isinstance(record[key], str) for key in RECORD_KEYS - {"size"}):
        raise BaselineError("manifest record has invalid string field")
    if not isinstance(record["size"], int) or record["size"] < 0:
        raise BaselineError("manifest record has invalid size")
    _safe_relative(str(record["path"]))
    if record["kind"] not in {"file", "symlink"}:
        raise BaselineError("manifest record has invalid kind")
    if not re.fullmatch(r"[0-7]{4}", str(record["mode"])):
        raise BaselineError("manifest record has invalid mode")
    if not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])):
        raise BaselineError("manifest record has invalid hash")
    return record


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineError("manifest is not valid JSON") from error
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise BaselineError(f"manifest schema must be {SCHEMA}")
    source = value.get("source")
    if not isinstance(source, dict):
        raise BaselineError("manifest source is missing")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("head", ""))):
        raise BaselineError("manifest source head is invalid")
    if not isinstance(source.get("branch"), str) or not source["branch"]:
        raise BaselineError("manifest source branch is invalid")
    records = value.get("records")
    if not isinstance(records, list):
        raise BaselineError("manifest records are missing")
    value["records"] = [_validate_record_shape(record) for record in records]
    for key in ("baseline_records", "imported_dirty_records"):
        optional_records = value.get(key, [])
        if not isinstance(optional_records, list):
            raise BaselineError(f"manifest {key} is invalid")
        value[key] = [
            _validate_record_shape(record) for record in optional_records
        ]
    for key in ("records", "baseline_records", "imported_dirty_records"):
        paths = [record["path"] for record in value[key]]
        if paths != sorted(set(paths)):
            raise BaselineError(f"manifest {key} paths must be sorted and unique")
    return value


def validate_records(root: Path, records: list[dict[str, object]]) -> None:
    for expected in records:
        actual = file_record(root, str(expected["path"]))
        if actual["sha256"] != expected["sha256"]:
            raise BaselineError(
                f"hash mismatch for allowlisted path {expected['path']}"
            )
        for key in RECORD_KEYS - {"sha256"}:
            if actual[key] != expected[key]:
                raise BaselineError(
                    f"{key} mismatch for allowlisted path {expected['path']}"
                )


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary.write_text(payload, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def create_archive(
    source: Path,
    records: list[dict[str, object]],
    archive: Path,
    receipt: Path,
    *,
    interrupt_after: int | None = None,
) -> None:
    validate_records(source, records)
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_name(f".{archive.name}.partial")
    partial.unlink(missing_ok=True)
    receipt.unlink(missing_ok=True)
    try:
        with tarfile.open(partial, "w:gz") as bundle:
            for index, record in enumerate(records, start=1):
                if interrupt_after is not None and index > interrupt_after:
                    raise BaselineError("archive creation interrupted")
                bundle.add(
                    source / str(record["path"]),
                    arcname=str(record["path"]),
                    recursive=False,
                )
        os.chmod(partial, 0o600)
        partial.replace(archive)
        _write_json_atomic(
            receipt,
            {
                "archive": archive.name,
                "archive_sha256": sha256_bytes(archive.read_bytes()),
                "record_count": len(records),
                "status": "complete",
            },
        )
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def _extract_checked(
    archive: Path,
    destination: Path,
    records: list[dict[str, object]],
) -> None:
    expected = {str(record["path"]) for record in records}
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        actual = {member.name for member in members}
        extras = actual - expected
        missing = expected - actual
        if extras:
            raise BaselineError(f"archive contains unlisted member: {min(extras)}")
        if missing:
            raise BaselineError(f"archive is missing member: {min(missing)}")
        for member in members:
            relative = _safe_relative(member.name)
            target = destination.joinpath(*relative.parts)
            if member.issym():
                resolved = (target.parent / member.linkname).resolve(strict=False)
                try:
                    resolved.relative_to(destination.resolve())
                except ValueError as error:
                    raise BaselineError(
                        f"archive symlink escapes restore: {member.name}"
                    ) from error
        bundle.extractall(destination, filter="data")


def verify_restore(
    restored: Path,
    records: list[dict[str, object]],
    *,
    archive: Path | None = None,
) -> None:
    if archive is not None:
        _extract_checked(archive, restored, records)
    validate_records(restored, records)


def verify_receipt(
    receipt_path: Path,
    archive: Path,
    manifest: dict[str, object],
) -> None:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineError("completion receipt is missing or malformed") from error
    archive_hash = sha256_bytes(archive.read_bytes())
    if receipt.get("status") != "complete":
        raise BaselineError("archive completion receipt is not complete")
    if receipt.get("archive_sha256") != archive_hash:
        raise BaselineError("archive receipt hash mismatch")
    if manifest.get("archive_sha256") != archive_hash:
        raise BaselineError("manifest archive hash mismatch")


def import_records(
    source: Path,
    clone: Path,
    records: list[dict[str, object]],
) -> None:
    validate_records(source, records)
    for record in records:
        relative = str(record["path"])
        origin = source / relative
        target = clone / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if record["kind"] == "symlink":
            target.unlink(missing_ok=True)
            target.symlink_to(os.readlink(origin))
        else:
            shutil.copy2(origin, target, follow_symlinks=False)
    validate_records(clone, records)


def run_bounded(command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise BaselineError(
            f"command timed out after {timeout_seconds:g}s"
        ) from error
