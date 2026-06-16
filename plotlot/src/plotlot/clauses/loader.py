"""YAML clause loader and in-memory registry.

Reads clause definition files from the definitions/ directory, validates
them against the ContractClause Pydantic model, and provides filtered
access by document type and deal type.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from plotlot.clauses.schema import ContractClause, DealType, DocumentType

logger = logging.getLogger(__name__)

# Default definitions directory (relative to this file)
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


def _load_reference_yaml(path: Path) -> dict:
    """Load a reference YAML file (prefixed with '_') and return its data."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data or {}
    except Exception:
        logger.exception("Failed to load reference file: %s", path)
        return {}


def load_clauses(directory: Path | None = None) -> list[ContractClause]:
    """Load all clause YAML files from the given directory tree.

    Recursively scans for .yaml/.yml files, skipping files that start
    with '_' (category definitions, state variants, etc.).

    Args:
        directory: Root directory to scan. Defaults to definitions/.

    Returns:
        List of validated ContractClause objects.
    """
    root = directory or _DEFINITIONS_DIR
    if not root.is_dir():
        logger.warning("Clause definitions directory not found: %s", root)
        return []

    clauses: list[ContractClause] = []

    for yaml_path in sorted(root.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        try:
            clauses.extend(_load_file(yaml_path))
        except Exception:
            logger.exception("Failed to load clause file: %s", yaml_path)

    for yaml_path in sorted(root.rglob("*.yml")):
        if yaml_path.name.startswith("_"):
            continue
        try:
            clauses.extend(_load_file(yaml_path))
        except Exception:
            logger.exception("Failed to load clause file: %s", yaml_path)

    logger.info("Loaded %d clauses from %s", len(clauses), root)
    return clauses


def _load_file(path: Path) -> list[ContractClause]:
    """Load one or more clauses from a single YAML file.

    A YAML file can contain a single clause dict or a list of clause dicts.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    if data is None:
        return []

    items: list[dict] = data if isinstance(data, list) else [data]
    clauses: list[ContractClause] = []

    for item in items:
        try:
            clause = ContractClause.model_validate(item)
            clauses.append(clause)
        except ValidationError as e:
            logger.warning("Invalid clause in %s: %s", path, e)

    return clauses


class ClauseRegistry:
    """In-memory registry of loaded clauses with filtering methods.

    Usage::

        registry = ClauseRegistry.from_directory()
        loi_clauses = registry.get(DocumentType.loi, DealType.land_deal)
    """

    def __init__(self, clauses: list[ContractClause]) -> None:
        self._clauses = clauses
        self._by_id: dict[str, ContractClause] = {c.id: c for c in clauses}
        self._state_terminology: dict[str, str] = {}
        self._categories: dict[str, dict] = {}

    @classmethod
    def from_directory(cls, directory: Path | None = None) -> ClauseRegistry:
        """Load clauses from YAML files and build a registry."""
        registry = cls(load_clauses(directory))
        root = directory or _DEFINITIONS_DIR
        if root.is_dir():
            state_path = root / "_state_variants.yaml"
            if state_path.exists():
                data = _load_reference_yaml(state_path)
                registry._state_terminology = data.get("state_terminology", {})
            cat_path = root / "_categories.yaml"
            if cat_path.exists():
                data = _load_reference_yaml(cat_path)
                registry._categories = data.get("categories", {})
        return registry

    @property
    def all_clauses(self) -> list[ContractClause]:
        """Return all loaded clauses."""
        return list(self._clauses)

    def get_by_id(self, clause_id: str) -> ContractClause | None:
        """Look up a single clause by its id."""
        return self._by_id.get(clause_id)

    def get(
        self,
        document_type: DocumentType,
        deal_type: DealType | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[ContractClause]:
        """Return clauses matching a document type and optional deal type.

        Args:
            document_type: Required document type filter.
            deal_type: Optional deal type filter. If None, all deal types match.
            exclude_ids: Clause IDs to exclude.

        Returns:
            Filtered list of ContractClause objects (unsorted — engine sorts).
        """
        excluded = set(exclude_ids or [])
        result: list[ContractClause] = []

        for clause in self._clauses:
            if clause.id in excluded:
                continue
            if document_type not in clause.document_types:
                continue
            if deal_type is not None and deal_type not in clause.deal_types:
                continue
            result.append(clause)

        return result

    def get_groups(self, clauses: list[ContractClause]) -> dict[str, list[ContractClause]]:
        """Group clauses by their group_id (non-None only)."""
        groups: dict[str, list[ContractClause]] = {}
        for clause in clauses:
            if clause.group_id:
                groups.setdefault(clause.group_id, []).append(clause)
        return groups

    @property
    def state_terminology(self) -> dict[str, str]:
        """Per-state terminology map loaded from _state_variants.yaml."""
        return dict(self._state_terminology)

    @property
    def categories(self) -> dict[str, dict]:
        """Category metadata loaded from _categories.yaml."""
        return {k: dict(v) for k, v in self._categories.items()}

    def __len__(self) -> int:
        return len(self._clauses)

    def __repr__(self) -> str:
        return f"ClauseRegistry({len(self._clauses)} clauses)"
