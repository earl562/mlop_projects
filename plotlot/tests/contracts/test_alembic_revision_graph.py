from __future__ import annotations

import ast
from pathlib import Path


VERSIONS_DIR = Path(__file__).parents[2] / "alembic" / "versions"


def _revision_value(path: Path, name: str) -> str | tuple[str, ...] | None:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name} does not declare {name}")


def test_alembic_revision_ids_are_unique_with_one_head() -> None:
    revisions: dict[str, Path] = {}
    referenced_parents: set[str] = set()

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        revision = _revision_value(path, "revision")
        assert isinstance(revision, str)
        assert revision not in revisions, (
            f"duplicate revision {revision}: {revisions[revision].name}, {path.name}"
        )
        revisions[revision] = path

        parent = _revision_value(path, "down_revision")
        if isinstance(parent, str):
            referenced_parents.add(parent)
        elif isinstance(parent, tuple):
            referenced_parents.update(parent)

    assert set(revisions) - referenced_parents == {
        "011_add_district_dimensional_standards"
    }
