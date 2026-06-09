"""Source adapters for ingesting zoning ordinances from different source types.

Public interface:
    SourceAdapter        — abstract base class
    MunicodeAdapter      — Municode REST API (88+ municipalities)
    PDFAdapter           — PDF files at known URLs
    PDFSource            — URL + metadata for a single PDF
    HTMLAdapter          — raw HTML pages
    resolve_adapter      — auto-detect the right adapter for any municipality
    register_pdf_municipality — register a new PDF-only municipality at runtime
"""

from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.html import HTMLAdapter
from plotlot.ingestion.adapters.municode import MunicodeAdapter
from plotlot.ingestion.adapters.pdf import PDFAdapter, PDFSource
from plotlot.ingestion.adapters.registry import register_pdf_municipality, resolve_adapter

__all__ = [
    "SourceAdapter",
    "MunicodeAdapter",
    "PDFAdapter",
    "PDFSource",
    "HTMLAdapter",
    "resolve_adapter",
    "register_pdf_municipality",
]
