from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

from plotlot_baseline_lib import BaselineError, sha256_bytes


def _fingerprint_includes(path: str) -> bool:
    return path != ".omo" and not path.startswith(".omo/")


def _status_without_runtime_evidence(status: bytes) -> bytes:
    kept: list[bytes] = []
    skip_rename_source = False
    for entry in status.split(b"\0"):
        if not entry:
            continue
        if skip_rename_source:
            skip_rename_source = False
            continue
        if entry.startswith(b"# "):
            kept.append(entry)
            continue
        if entry.startswith((b"? ", b"! ")):
            raw_path = entry[2:]
        elif entry.startswith(b"1 "):
            raw_path = entry.split(b" ", 8)[-1]
        elif entry.startswith(b"2 "):
            raw_path = entry.split(b" ", 9)[-1]
            skip_rename_source = True
        else:
            kept.append(entry)
            continue
        path = raw_path.decode("utf-8", "surrogateescape")
        if _fingerprint_includes(path):
            kept.append(entry)
    return b"\0".join(kept) + b"\0"


def git_bytes(repo: Path, *arguments: str, timeout_seconds: float = 30) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise BaselineError(
            f"git command timed out after {timeout_seconds:g}s"
        ) from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.decode("utf-8", "replace").strip()
        raise BaselineError(f"git command failed: {message}") from error
    return result.stdout


def _fingerprint_record(root: Path, path: str) -> dict[str, object]:
    target = root / path
    metadata = target.lstat()
    mode = f"{stat.S_IMODE(metadata.st_mode):04o}"
    if stat.S_ISLNK(metadata.st_mode):
        payload = os.readlink(target).encode("utf-8", "surrogateescape")
        kind = "symlink"
    elif stat.S_ISREG(metadata.st_mode):
        payload = target.read_bytes()
        kind = "file"
    else:
        raise BaselineError(f"unsupported fingerprint file kind: {path}")
    return {
        "path": path,
        "kind": kind,
        "mode": mode,
        "sha256": sha256_bytes(payload),
        "size": len(payload),
    }


def _common_git_dir(repo: Path) -> Path:
    raw = git_bytes(repo, "rev-parse", "--git-common-dir").decode().strip()
    return (repo / raw).resolve() if not Path(raw).is_absolute() else Path(raw)


def source_fingerprint(repo: Path) -> dict[str, object]:
    head = git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    branch = git_bytes(repo, "branch", "--show-current").decode().strip()
    raw_status = git_bytes(
        repo,
        "status",
        "--porcelain=v2",
        "-z",
        "--branch",
        "--untracked-files=all",
    )
    status = _status_without_runtime_evidence(raw_status)
    diff = git_bytes(repo, "diff", "--binary", timeout_seconds=60)
    dirty_raw = git_bytes(
        repo,
        "ls-files",
        "-m",
        "-o",
        "--exclude-standard",
        "-z",
    )
    dirty_paths = sorted(
        path.decode("utf-8", "surrogateescape")
        for path in dirty_raw.split(b"\0")
        if path
        and _fingerprint_includes(path.decode("utf-8", "surrogateescape"))
    )
    dirty_digest = hashlib.sha256()
    for path in dirty_paths:
        record = _fingerprint_record(repo, path)
        dirty_digest.update(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        )
        dirty_digest.update(b"\n")
    common = _common_git_dir(repo)
    metadata_digest = hashlib.sha256()
    metadata_paths = [
        common / "HEAD",
        common / "config",
        common / "packed-refs",
        common / "refs" / "heads" / branch,
        common / "objects" / "info" / "alternates",
    ]
    for path in metadata_paths:
        metadata_digest.update(str(path.relative_to(common)).encode())
        metadata_digest.update(b"\0")
        if path.is_file():
            metadata_digest.update(path.read_bytes())
        metadata_digest.update(b"\0")
    return {
        "head": head,
        "branch": branch,
        "status_sha256": sha256_bytes(status),
        "diff_sha256": sha256_bytes(diff),
        "diff_bytes": len(diff),
        "dirty_record_count": len(dirty_paths),
        "dirty_records_sha256": dirty_digest.hexdigest(),
        "git_common_sha256": metadata_digest.hexdigest(),
    }


def assert_no_alternates(repo: Path) -> None:
    alternates = _common_git_dir(repo) / "objects" / "info" / "alternates"
    if alternates.exists() and alternates.read_bytes().strip():
        raise BaselineError(f"Git alternates configured in {repo}")
    configured = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            "--get",
            "objects.alternateObjectDirectories",
        ],
        capture_output=True,
        check=False,
    )
    if configured.returncode == 0 and configured.stdout.strip():
        raise BaselineError(f"Git alternate object directory configured in {repo}")


def assert_no_shared_object_inodes(source: Path, clone: Path) -> int:
    source_objects = _common_git_dir(source) / "objects"
    clone_objects = _common_git_dir(clone) / "objects"
    source_inodes = {
        (path.stat().st_dev, path.stat().st_ino)
        for path in source_objects.rglob("*")
        if path.is_file()
    }
    clone_files = [path for path in clone_objects.rglob("*") if path.is_file()]
    for path in clone_files:
        identity = (path.stat().st_dev, path.stat().st_ino)
        if identity in source_inodes:
            raise BaselineError(f"shared Git object inode detected: {path.name}")
    return len(clone_files)
