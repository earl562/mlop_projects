"""Tests for YAML clause loader and ClauseRegistry."""

from pathlib import Path

import yaml

from plotlot.clauses.loader import ClauseRegistry, load_clauses
from plotlot.clauses.schema import DealType, DocumentType


def _write_clause_yaml(directory: Path, filename: str, data: dict | list) -> Path:
    """Write a clause YAML file to a temp directory."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def _sample_clause(
    clause_id: str = "test.sample",
    document_types: list[str] | None = None,
    deal_types: list[str] | None = None,
    **overrides,
) -> dict:
    """Build a minimal valid clause dict."""
    return {
        "id": clause_id,
        "category": "financial_terms",
        "title": f"Test Clause {clause_id}",
        "document_types": document_types or ["loi"],
        "deal_types": deal_types or ["land_deal", "wholesale"],
        "content_template": "Price: {{ context.purchase_price }}",
        "order_weight": 100,
        **overrides,
    }


# ---------------------------------------------------------------------------
# load_clauses
# ---------------------------------------------------------------------------


class TestLoadClauses:
    def test_empty_directory(self, tmp_path):
        clauses = load_clauses(tmp_path)
        assert clauses == []

    def test_nonexistent_directory(self, tmp_path):
        clauses = load_clauses(tmp_path / "nope")
        assert clauses == []

    def test_single_clause_file(self, tmp_path):
        _write_clause_yaml(tmp_path, "price.yaml", _sample_clause("loi.price"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 1
        assert clauses[0].id == "loi.price"

    def test_multiple_clauses_in_one_file(self, tmp_path):
        data = [
            _sample_clause("loi.price"),
            _sample_clause("loi.earnest"),
        ]
        _write_clause_yaml(tmp_path, "financial.yaml", data)
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 2

    def test_nested_directories(self, tmp_path):
        _write_clause_yaml(tmp_path / "loi", "price.yaml", _sample_clause("loi.price"))
        _write_clause_yaml(tmp_path / "psa", "parties.yaml", _sample_clause("psa.parties"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 2
        ids = {c.id for c in clauses}
        assert ids == {"loi.price", "psa.parties"}

    def test_skips_underscore_files(self, tmp_path):
        _write_clause_yaml(tmp_path, "_categories.yaml", {"categories": {}})
        _write_clause_yaml(tmp_path, "price.yaml", _sample_clause("loi.price"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 1

    def test_skips_invalid_clauses(self, tmp_path):
        _write_clause_yaml(tmp_path, "bad.yaml", {"id": "missing_required_fields"})
        _write_clause_yaml(tmp_path, "good.yaml", _sample_clause("loi.good"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 1
        assert clauses[0].id == "loi.good"

    def test_empty_yaml_file(self, tmp_path):
        (tmp_path / "empty.yaml").write_text("")
        clauses = load_clauses(tmp_path)
        assert clauses == []

    def test_yml_extension(self, tmp_path):
        _write_clause_yaml(tmp_path, "price.yml", _sample_clause("loi.price"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 1


# ---------------------------------------------------------------------------
# ClauseRegistry
# ---------------------------------------------------------------------------


class TestClauseRegistry:
    def _build_registry(self, tmp_path) -> ClauseRegistry:
        """Build a registry with 4 test clauses."""
        clauses = [
            _sample_clause("loi.price", document_types=["loi"], deal_types=["land_deal"]),
            _sample_clause(
                "loi.parties", document_types=["loi"], deal_types=["land_deal", "wholesale"]
            ),
            _sample_clause("psa.price", document_types=["psa"], deal_types=["subject_to", "wrap"]),
            _sample_clause(
                "psa.financing_subto",
                document_types=["psa"],
                deal_types=["subject_to"],
                group_id="financing_type",
            ),
        ]
        for c in clauses:
            _write_clause_yaml(tmp_path / "test", f"{c['id'].replace('.', '_')}.yaml", c)
        return ClauseRegistry.from_directory(tmp_path / "test")

    def test_len(self, tmp_path):
        registry = self._build_registry(tmp_path)
        assert len(registry) == 4

    def test_get_by_document_type(self, tmp_path):
        registry = self._build_registry(tmp_path)
        loi_clauses = registry.get(DocumentType.loi)
        assert len(loi_clauses) == 2
        assert all(DocumentType.loi in c.document_types for c in loi_clauses)

    def test_get_by_document_and_deal_type(self, tmp_path):
        registry = self._build_registry(tmp_path)
        psa_subto = registry.get(DocumentType.psa, DealType.subject_to)
        assert len(psa_subto) == 2

    def test_get_no_match(self, tmp_path):
        registry = self._build_registry(tmp_path)
        result = registry.get(DocumentType.deal_summary)
        assert result == []

    def test_get_with_exclude(self, tmp_path):
        registry = self._build_registry(tmp_path)
        result = registry.get(DocumentType.loi, exclude_ids=["loi.price"])
        assert len(result) == 1
        assert result[0].id == "loi.parties"

    def test_get_by_id(self, tmp_path):
        registry = self._build_registry(tmp_path)
        clause = registry.get_by_id("psa.price")
        assert clause is not None
        assert clause.id == "psa.price"

    def test_get_by_id_missing(self, tmp_path):
        registry = self._build_registry(tmp_path)
        assert registry.get_by_id("nonexistent") is None

    def test_get_groups(self, tmp_path):
        registry = self._build_registry(tmp_path)
        all_psa = registry.get(DocumentType.psa)
        groups = registry.get_groups(all_psa)
        assert "financing_type" in groups
        assert len(groups["financing_type"]) == 1

    def test_repr(self, tmp_path):
        registry = self._build_registry(tmp_path)
        assert "4 clauses" in repr(registry)


# ---------------------------------------------------------------------------
# Comprehensive tests — Happy Path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Happy-path tests covering real definitions and filtering logic."""

    def test_load_from_directory_count(self):
        """Load clauses from the real YAML definitions directory — at least 20."""
        registry = ClauseRegistry.from_directory()
        assert len(registry) >= 20, f"Expected >=20 clauses, got {len(registry)}"

    def test_registry_filters_by_doc_type(self, tmp_path):
        """Query for DocumentType.loi returns only LOI clauses."""
        clauses = [
            _sample_clause("loi.a", document_types=["loi"]),
            _sample_clause("psa.b", document_types=["psa"]),
            _sample_clause("loi.c", document_types=["loi"]),
        ]
        for c in clauses:
            _write_clause_yaml(tmp_path, f"{c['id'].replace('.', '_')}.yaml", c)
        registry = ClauseRegistry.from_directory(tmp_path)

        loi_results = registry.get(DocumentType.loi)
        assert len(loi_results) == 2
        assert all(DocumentType.loi in c.document_types for c in loi_results)
        assert all(c.id.startswith("loi.") for c in loi_results)

    def test_registry_filters_by_deal_type(self, tmp_path):
        """Query for DealType.subject_to returns only subject_to clauses."""
        clauses = [
            _sample_clause("psa.subto", document_types=["psa"], deal_types=["subject_to"]),
            _sample_clause("psa.land", document_types=["psa"], deal_types=["land_deal"]),
            _sample_clause("psa.both", document_types=["psa"], deal_types=["subject_to", "wrap"]),
        ]
        for c in clauses:
            _write_clause_yaml(tmp_path, f"{c['id'].replace('.', '_')}.yaml", c)
        registry = ClauseRegistry.from_directory(tmp_path)

        subto_results = registry.get(DocumentType.psa, DealType.subject_to)
        assert len(subto_results) == 2
        ids = {c.id for c in subto_results}
        assert ids == {"psa.subto", "psa.both"}
        assert all(DealType.subject_to in c.deal_types for c in subto_results)

    def test_underscore_files_skipped(self, tmp_path):
        """Files starting with '_' in clause directory are ignored."""
        _write_clause_yaml(tmp_path, "_categories.yaml", {"categories": {"finance": "Finance"}})
        _write_clause_yaml(tmp_path, "_state_variants.yaml", [{"FL": "Florida version"}])
        _write_clause_yaml(tmp_path, "good.yaml", _sample_clause("test.good"))
        clauses = load_clauses(tmp_path)
        assert len(clauses) == 1
        assert clauses[0].id == "test.good"

    def test_multiple_document_types(self, tmp_path):
        """A clause with multiple doc_types appears in both LOI and PSA queries."""
        shared_clause = _sample_clause(
            "shared.governing_law",
            document_types=["loi", "psa"],
            deal_types=["land_deal"],
        )
        loi_only = _sample_clause("loi.price", document_types=["loi"])
        psa_only = _sample_clause("psa.parties", document_types=["psa"])
        for c in [shared_clause, loi_only, psa_only]:
            _write_clause_yaml(tmp_path, f"{c['id'].replace('.', '_')}.yaml", c)
        registry = ClauseRegistry.from_directory(tmp_path)

        loi_results = registry.get(DocumentType.loi)
        psa_results = registry.get(DocumentType.psa)

        loi_ids = {c.id for c in loi_results}
        psa_ids = {c.id for c in psa_results}

        assert "shared.governing_law" in loi_ids
        assert "shared.governing_law" in psa_ids
        assert "loi.price" in loi_ids
        assert "loi.price" not in psa_ids
        assert "psa.parties" in psa_ids
        assert "psa.parties" not in loi_ids


# ---------------------------------------------------------------------------
# Comprehensive tests — Unhappy Path
# ---------------------------------------------------------------------------


class TestUnhappyPath:
    """Unhappy-path tests for error handling and edge cases."""

    def test_invalid_yaml_logged_not_crash(self, tmp_path, caplog):
        """Invalid YAML is logged but doesn't crash; other clauses still load."""
        # Write a file with invalid YAML syntax
        bad_file = tmp_path / "broken.yaml"
        bad_file.write_text("{{invalid yaml: [unclosed")

        _write_clause_yaml(tmp_path, "good.yaml", _sample_clause("test.good"))

        with caplog.at_level("WARNING", logger="plotlot.clauses.loader"):
            clauses = load_clauses(tmp_path)

        # Good clause still loaded
        assert len(clauses) == 1
        assert clauses[0].id == "test.good"
        # Error was logged (at ERROR level via logger.exception)
        assert any("broken.yaml" in r.message for r in caplog.records)

    def test_missing_content_template_skipped(self, tmp_path, caplog):
        """Clause YAML missing content_template is skipped; rest load fine."""
        bad_clause = {
            "id": "test.no_template",
            "category": "financial_terms",
            "title": "Missing Template",
            "document_types": ["loi"],
            # content_template intentionally omitted
        }
        _write_clause_yaml(tmp_path, "bad.yaml", bad_clause)
        _write_clause_yaml(tmp_path, "good.yaml", _sample_clause("test.good"))

        with caplog.at_level("WARNING", logger="plotlot.clauses.loader"):
            clauses = load_clauses(tmp_path)

        assert len(clauses) == 1
        assert clauses[0].id == "test.good"
        # Validation warning was logged
        assert any("bad.yaml" in r.message for r in caplog.records)

    def test_extra_unknown_fields_ignored(self, tmp_path):
        """Clause with extra fields not in schema — Pydantic ignores them."""
        clause_data = _sample_clause(
            "test.extra_fields",
            bogus_field="should be ignored",
            another_unknown=42,
            nested_junk={"key": "value"},
        )
        _write_clause_yaml(tmp_path, "extra.yaml", clause_data)
        clauses = load_clauses(tmp_path)

        assert len(clauses) == 1
        assert clauses[0].id == "test.extra_fields"
        assert not hasattr(clauses[0], "bogus_field")
        assert not hasattr(clauses[0], "another_unknown")

    def test_empty_directory_returns_empty(self, tmp_path):
        """Load from empty temp directory returns empty list, no error."""
        empty_dir = tmp_path / "empty_clauses"
        empty_dir.mkdir()
        registry = ClauseRegistry.from_directory(empty_dir)
        assert len(registry) == 0
        assert registry.all_clauses == []

    def test_query_nonexistent_doc_type_returns_empty(self, tmp_path):
        """Query for doc type with no matching clauses returns empty list."""
        _write_clause_yaml(
            tmp_path, "loi.yaml", _sample_clause("loi.price", document_types=["loi"])
        )
        _write_clause_yaml(
            tmp_path, "psa.yaml", _sample_clause("psa.parties", document_types=["psa"])
        )
        registry = ClauseRegistry.from_directory(tmp_path)

        result = registry.get(DocumentType.deal_summary)
        assert result == []

        result = registry.get(DocumentType.promissory_note)
        assert result == []

        result = registry.get(DocumentType.addendum)
        assert result == []
