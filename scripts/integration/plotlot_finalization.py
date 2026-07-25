from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from plotlot_baseline_lib import BaselineError
from plotlot_git_integrity import git_bytes

SCHEMA = "PlotLotFinalizationV1"
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class CloneBinding(TypedDict):
    head: str
    branch: str


class ArtifactBindings(TypedDict):
    manifest_sha256: str
    archive_sha256: str
    completion_receipt_sha256: str


class FinalizationBody(TypedDict):
    schema: str
    clone: CloneBinding
    bindings: ArtifactBindings


class FinalizationReceipt(FinalizationBody):
    integrity_sha256: str


@dataclass(frozen=True, slots=True)
class FinalizationPaths:
    clone: Path
    manifest: Path
    archive: Path
    completion_receipt: Path
    finalization_receipt: Path


def _sha256_file(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise BaselineError(f"{label} is missing") from error


def _required_branch(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineError("manifest is missing or malformed") from error
    if not isinstance(value, dict):
        raise BaselineError("manifest required clone branch is missing")
    branch = value.get("required_clone_branch")
    if not isinstance(branch, str) or not branch:
        raise BaselineError("manifest required clone branch is missing")
    return branch


def _canonical_hash(value: FinalizationBody) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _body(paths: FinalizationPaths) -> FinalizationBody:
    branch = git_bytes(paths.clone, "branch", "--show-current").decode().strip()
    required_branch = _required_branch(paths.manifest)
    if branch != required_branch:
        raise BaselineError("clone branch drift from manifest requirement")
    return {
        "schema": SCHEMA,
        "clone": {
            "head": git_bytes(paths.clone, "rev-parse", "HEAD").decode().strip(),
            "branch": branch,
        },
        "bindings": {
            "manifest_sha256": _sha256_file(paths.manifest, "manifest"),
            "archive_sha256": _sha256_file(paths.archive, "archive"),
            "completion_receipt_sha256": _sha256_file(
                paths.completion_receipt,
                "completion receipt",
            ),
        },
    }


def _load_receipt(path: Path) -> FinalizationReceipt:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineError("finalization receipt is missing or malformed") from error
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "clone",
        "bindings",
        "integrity_sha256",
    }:
        raise BaselineError("finalization receipt has invalid shape")
    clone = value["clone"]
    bindings = value["bindings"]
    integrity = value["integrity_sha256"]
    if (
        value["schema"] != SCHEMA
        or not isinstance(clone, dict)
        or set(clone) != {"head", "branch"}
        or not all(isinstance(item, str) and item for item in clone.values())
        or not isinstance(bindings, dict)
        or set(bindings)
        != {
            "manifest_sha256",
            "archive_sha256",
            "completion_receipt_sha256",
        }
        or not all(isinstance(item, str) and item for item in bindings.values())
        or not isinstance(integrity, str)
    ):
        raise BaselineError("finalization receipt has invalid shape")
    return value


def write_json(path: Path, value: FinalizationReceipt | JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def create_finalization_receipt(paths: FinalizationPaths) -> None:
    body = _body(paths)
    receipt: FinalizationReceipt = {
        **body,
        "integrity_sha256": _canonical_hash(body),
    }
    write_json(paths.finalization_receipt, receipt)


def verify_finalization_receipt(paths: FinalizationPaths) -> None:
    receipt = _load_receipt(paths.finalization_receipt)
    body: FinalizationBody = {
        "schema": receipt["schema"],
        "clone": receipt["clone"],
        "bindings": receipt["bindings"],
    }
    if receipt["integrity_sha256"] != _canonical_hash(body):
        raise BaselineError("finalization receipt integrity mismatch")
    expected = _body(paths)
    if receipt["bindings"] != expected["bindings"]:
        raise BaselineError("finalization artifact binding drift")
    if receipt["clone"]["branch"] != expected["clone"]["branch"]:
        raise BaselineError("clone branch drift from finalization receipt")
    if receipt["clone"]["head"] != expected["clone"]["head"]:
        raise BaselineError("clone commit drift from finalization receipt")


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind a PlotLot baseline to the current clone commit and branch."
    )
    parser.add_argument("--clone", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--completion-receipt", required=True)
    parser.add_argument("--finalization-receipt", required=True)
    args = parser.parse_args()
    paths = FinalizationPaths(
        clone=_path(args.clone),
        manifest=_path(args.manifest),
        archive=_path(args.archive),
        completion_receipt=_path(args.completion_receipt),
        finalization_receipt=_path(args.finalization_receipt),
    )
    try:
        create_finalization_receipt(paths)
    except BaselineError as error:
        print(f"FINALIZATION_FAILED: {error}")
        return 1
    print("FINALIZATION_OK=true")
    print(f"CLONE_HEAD={git_bytes(paths.clone, 'rev-parse', 'HEAD').decode().strip()}")
    print(
        "CLONE_BRANCH="
        f"{git_bytes(paths.clone, 'branch', '--show-current').decode().strip()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
