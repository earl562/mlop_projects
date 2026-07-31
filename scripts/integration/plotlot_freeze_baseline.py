#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from plotlot_baseline_lib import (
    SCHEMA,
    BaselineError,
    create_archive,
    file_record,
    import_records,
    load_manifest,
    scan_secret_bytes,
    sha256_bytes,
    validate_records,
    verify_receipt,
    verify_restore,
)
from plotlot_git_integrity import (
    assert_no_alternates,
    assert_no_shared_object_inodes,
    git_bytes,
    source_fingerprint,
)
from plotlot_finalization import FinalizationPaths, verify_finalization_receipt, write_json
from plotlot_repository_policy import (
    assert_ignored_paths_allowed,
    assert_no_prohibited_tracked_artifacts,
    assert_records_exclude_artifacts,
    reject_disposable_ignored_fixture,
)


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _reviewed_paths(path: Path) -> list[str]:
    values = path.read_text(encoding="utf-8").splitlines()
    if not values or values != sorted(set(values)):
        raise BaselineError("reviewed path list must be nonempty, sorted, and unique")
    return values


def _scan_records(root: Path, records: list[dict[str, str | int]]) -> None:
    for record in records:
        path = str(record["path"])
        target = root / path
        if record["kind"] == "file":
            scan_secret_bytes(target.read_bytes(), path)


def capture(args: argparse.Namespace) -> None:
    source = _path(args.source)
    clone = _path(args.clone)
    paths_file = _path(args.paths_file)
    manifest_path = _path(args.manifest)
    archive = _path(args.archive)
    receipt = _path(args.receipt)
    paths = _reviewed_paths(paths_file)
    records = [file_record(source, path) for path in paths]
    baseline_paths = _reviewed_paths(_path(args.baseline_paths_file))
    baseline_root = _path(args.baseline_root)
    baseline_records = [file_record(baseline_root, path) for path in baseline_paths]
    source_ignored_count = assert_ignored_paths_allowed(source)
    baseline_ignored_count = assert_ignored_paths_allowed(baseline_root)
    clone_ignored_count = assert_ignored_paths_allowed(clone)
    assert_no_prohibited_tracked_artifacts(clone)
    assert_records_exclude_artifacts(records)
    assert_records_exclude_artifacts(baseline_records)
    _scan_records(source, records)
    _scan_records(baseline_root, baseline_records)
    fingerprint = source_fingerprint(source)
    clone_branch = git_bytes(clone, "branch", "--show-current").decode().strip()
    create_archive(source, records, archive, receipt)
    archive_hash = sha256_bytes(archive.read_bytes())
    path_list_hash = sha256_bytes(("\n".join(paths) + "\n").encode())
    manifest = {
        "schema": SCHEMA,
        "source": {
            "head": fingerprint["head"],
            "branch": fingerprint["branch"],
        },
        "source_fingerprint": fingerprint,
        "required_clone_branch": clone_branch,
        "reviewed_paths_sha256": path_list_hash,
        "baseline_paths_sha256": sha256_bytes(
            ("\n".join(baseline_paths) + "\n").encode()
        ),
        "archive_sha256": archive_hash,
        "records": records,
        "baseline_records": baseline_records,
        "imported_dirty_records": [],
        "repository_policy": "PlotLotRepositoryPolicyV1",
        "reviewed_path_classes": {
            "plotlot/src/**": "runtime closure for the approved PlotLot MVP",
            "plotlot/tests/**": "characterization and regression coverage for that runtime",
            "plotlot/frontend/src/**": "customer-host UI dependencies changed with the runtime",
            "plotlot/frontend/tests/**": "regression coverage for imported host UI behavior",
            "plotlot/alembic/versions/**": "schema dependencies required by imported persistence code",
            "plotlot/pyproject.toml": "Python dependency and command contract",
            "plotlot/uv.lock": "reproducible Python dependency resolution",
            "plotlot/.env.example": "non-secret configuration-name contract",
        },
        "exclusions": [
            ".omo and prior evidence",
            "caches, environments, node_modules, and build outputs",
            "secrets and local credentials including .env",
            "generated media, dumps, and unrelated user documents",
        ],
    }
    write_json(manifest_path, manifest)
    print(f"CAPTURE_OK records={len(records)}")
    print(f"SOURCE_HEAD={fingerprint['head']}")
    print(f"SOURCE_FINGERPRINT={fingerprint['dirty_records_sha256']}")
    print(f"ALLOWLIST_SHA256={path_list_hash}")
    print(f"ARCHIVE_SHA256={archive_hash}")
    print(
        "IGNORED_PATH_POLICY=pass "
        f"source={source_ignored_count} baseline={baseline_ignored_count} "
        f"clone={clone_ignored_count}"
    )


def import_baseline(args: argparse.Namespace) -> None:
    source = _path(args.source)
    clone = _path(args.clone)
    baseline_root = _path(args.baseline_root)
    manifest = load_manifest(_path(args.manifest))
    fingerprint = source_fingerprint(source)
    if fingerprint != manifest.get("source_fingerprint"):
        raise BaselineError("source fingerprint changed since capture")
    dirty_records = manifest["imported_dirty_records"]
    baseline_records = manifest["baseline_records"]
    source_ignored_count = assert_ignored_paths_allowed(source)
    baseline_ignored_count = assert_ignored_paths_allowed(baseline_root)
    clone_ignored_count = assert_ignored_paths_allowed(clone)
    assert_no_prohibited_tracked_artifacts(clone)
    assert_records_exclude_artifacts(manifest["records"])
    assert_records_exclude_artifacts(baseline_records)
    assert_records_exclude_artifacts(dirty_records)
    baseline_paths = {str(record["path"]) for record in baseline_records}
    _scan_records(source, dirty_records)
    _scan_records(baseline_root, baseline_records)
    for record in manifest["records"]:
        path = str(record["path"])
        target = clone / path
        if path not in baseline_paths and (target.is_file() or target.is_symlink()):
            target.unlink()
    import_records(baseline_root, clone, baseline_records)
    import_records(source, clone, dirty_records)
    print(
        f"IMPORT_OK baseline_records={len(baseline_records)} "
        f"dirty_records={len(dirty_records)}"
    )
    print("ALLOWLIST_HASHES_VERIFIED=true")
    print(
        "IGNORED_PATH_POLICY=pass "
        f"source={source_ignored_count} baseline={baseline_ignored_count} "
        f"clone={clone_ignored_count}"
    )


def verify(args: argparse.Namespace) -> None:
    if args.inject_secret_shape:
        scan_secret_bytes(
            b"OPENAI_API_KEY=sk-proj-" + (b"A" * 48),
            "disposable/injected-secret",
        )
    if args.inject_unallowlisted_ignored:
        reject_disposable_ignored_fixture()
    source = _path(args.source)
    clone = _path(args.clone)
    manifest_path = _path(args.manifest)
    archive = _path(args.archive)
    receipt = _path(args.receipt)
    finalization_receipt = _path(args.finalization_receipt)
    manifest = load_manifest(manifest_path)
    verify_finalization_receipt(
        FinalizationPaths(
            clone=clone,
            manifest=manifest_path,
            archive=archive,
            completion_receipt=receipt,
            finalization_receipt=finalization_receipt,
        )
    )
    records = manifest["records"]
    baseline_records = manifest["baseline_records"]
    imported_dirty_records = manifest["imported_dirty_records"]
    source_ignored_count = assert_ignored_paths_allowed(source)
    clone_ignored_count = assert_ignored_paths_allowed(clone)
    assert_no_prohibited_tracked_artifacts(clone)
    assert_records_exclude_artifacts(records)
    assert_records_exclude_artifacts(baseline_records)
    assert_records_exclude_artifacts(imported_dirty_records)
    fingerprint = source_fingerprint(source)
    if fingerprint != manifest.get("source_fingerprint"):
        raise BaselineError("source fingerprint changed since capture")
    _scan_records(source, records)
    validate_records(source, records)
    validate_records(clone, baseline_records)
    validate_records(clone, imported_dirty_records)
    verify_receipt(receipt, archive, manifest)
    with tempfile.TemporaryDirectory(prefix="plotlot-restore-") as raw:
        restore = Path(raw)
        verify_restore(restore, records, archive=archive)
    assert_no_alternates(source)
    assert_no_alternates(clone)
    object_count = assert_no_shared_object_inodes(source, clone)
    print("VALIDATION_OK=true")
    print("SOURCE_UNCHANGED=true")
    print("ALLOWLIST_HASHES_VERIFIED=true")
    print("FINALIZATION_BINDING_VERIFIED=true")
    print("RESTORE_IDENTITY_VERIFIED=true")
    print("NO_GIT_ALTERNATES=true")
    print(f"NO_SHARED_OBJECT_INODES=true compared_clone_objects={object_count}")
    print("SECRET_SCAN=pass")
    print(
        "IGNORED_PATH_POLICY=pass "
        f"source={source_ignored_count} clone={clone_ignored_count}"
    )


def parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--source", required=True)
    shared.add_argument("--clone", required=True)
    shared.add_argument("--manifest", required=True)
    root = argparse.ArgumentParser(
        description="Freeze and validate a hash-bound PlotLot repository baseline."
    )
    commands = root.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture", parents=[shared])
    capture_parser.add_argument("--paths-file", required=True)
    capture_parser.add_argument("--baseline-root", required=True)
    capture_parser.add_argument("--baseline-paths-file", required=True)
    capture_parser.add_argument("--archive", required=True)
    capture_parser.add_argument("--receipt", required=True)
    capture_parser.set_defaults(handler=capture)
    import_parser = commands.add_parser("import", parents=[shared])
    import_parser.add_argument("--baseline-root", required=True)
    import_parser.set_defaults(handler=import_baseline)
    verify_parser = commands.add_parser("verify", parents=[shared])
    verify_parser.add_argument("--archive", required=True)
    verify_parser.add_argument("--receipt", required=True)
    verify_parser.add_argument("--finalization-receipt", required=True)
    verify_parser.add_argument("--inject-secret-shape", action="store_true")
    verify_parser.add_argument(
        "--inject-unallowlisted-ignored",
        action="store_true",
    )
    verify_parser.set_defaults(handler=verify)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except BaselineError as error:
        print(f"VALIDATION_FAILED: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
