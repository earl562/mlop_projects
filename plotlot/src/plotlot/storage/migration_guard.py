from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MigrationGraphError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class Revision:
    revision: str
    parents: tuple[str, ...]


def validate_revision_graph(versions_dir: Path) -> str:
    revisions = tuple(_read_revision(path) for path in sorted(versions_dir.glob("*.py")))
    by_id: dict[str, Revision] = {}
    for item in revisions:
        if item.revision in by_id:
            raise MigrationGraphError(f"duplicate revision: {item.revision}")
        by_id[item.revision] = item

    referenced = {parent for item in revisions for parent in item.parents}
    missing = referenced.difference(by_id)
    if missing:
        raise MigrationGraphError(f"missing parent revisions: {sorted(missing)}")
    heads = sorted(set(by_id).difference(referenced))
    if len(heads) != 1:
        raise MigrationGraphError(f"expected one migration head, found: {heads}")
    return heads[0]


def _read_revision(path: Path) -> Revision:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision: str | None = None
    parents: tuple[str, ...] = ()
    for node in tree.body:
        name, value = _assignment(node)
        if name == "revision":
            revision = _string(value, path, name)
        if name == "down_revision":
            parents = _parents(value, path)
    if revision is None:
        raise MigrationGraphError(f"missing revision in {path.name}")
    return Revision(revision=revision, parents=parents)


def _assignment(node: ast.stmt) -> tuple[str | None, ast.expr | None]:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target.id, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id, node.value
    return None, None


def _string(value: ast.expr | None, path: Path, field: str) -> str:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    raise MigrationGraphError(f"{field} must be a string in {path.name}")


def _parents(value: ast.expr | None, path: Path) -> tuple[str, ...]:
    if isinstance(value, ast.Constant) and value.value is None:
        return ()
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return (value.value,)
    if isinstance(value, ast.Tuple):
        return tuple(_string(element, path, "down_revision") for element in value.elts)
    raise MigrationGraphError(f"invalid down_revision in {path.name}")
