"""Tests for deprecated functions and backward-compatible imports."""

import pytest

from plotlot.core.types import ZoningReport


def _minimal_report() -> ZoningReport:
    """Create a minimal ZoningReport for testing deprecated callables."""
    return ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Miami, FL 33101",
        municipality="Miami",
        county="Miami-Dade",
        zoning_district="T6-8",
        zoning_description="Urban Core",
    )


# ---------------------------------------------------------------------------
# Deprecation warnings
# ---------------------------------------------------------------------------


class TestDeprecationWarnings:
    def test_generate_loi_emits_deprecation(self):
        """generate_loi() should emit a DeprecationWarning on every call."""
        from plotlot.pipeline.contracts import generate_loi

        report = _minimal_report()
        with pytest.warns(DeprecationWarning, match="generate_loi.*deprecated"):
            generate_loi(report)

    def test_generate_deal_summary_emits_deprecation(self):
        """generate_deal_summary() should emit a DeprecationWarning on every call."""
        from plotlot.pipeline.contracts import generate_deal_summary

        report = _minimal_report()
        with pytest.warns(DeprecationWarning, match="generate_deal_summary.*deprecated"):
            generate_deal_summary(report)


# ---------------------------------------------------------------------------
# Backward-compatible imports
# ---------------------------------------------------------------------------


class TestBackwardCompatImports:
    def test_import_generated_document_from_contracts(self):
        """GeneratedDocument should be importable from the old location."""
        from plotlot.pipeline.contracts import GeneratedDocument

        assert GeneratedDocument is not None
        # Verify it's the same class as the canonical location
        from plotlot.clauses.schema import GeneratedDocument as Canonical

        assert GeneratedDocument is Canonical

    def test_import_generated_document_from_clauses(self):
        """GeneratedDocument should be importable from its canonical location."""
        from plotlot.clauses.schema import GeneratedDocument

        assert GeneratedDocument is not None
        # Verify it can be instantiated
        doc = GeneratedDocument(
            filename="test.docx",
            content_type="application/octet-stream",
            data=b"test",
        )
        assert doc.filename == "test.docx"
        assert doc.data == b"test"
