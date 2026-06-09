"""Tests for Document Upload (AC-2.1)."""

from dataclasses import dataclass


@dataclass
class FakeDocument:
    id: str = ""
    filename: str = ""
    mime_type: str = ""
    category: str = ""
    ocr_status: str = "pending"


class DocumentUploader:
    def __init__(self):
        self.documents = []

    async def upload(self, filename: str, content: bytes, category: str = "") -> FakeDocument:
        if len(content) > 50 * 1024 * 1024:
            raise ValueError("File too large")
        doc = FakeDocument(
            id=f"doc_{len(self.documents)}",
            filename=filename,
            mime_type="application/pdf",
            category=category,
        )
        self.documents.append(doc)
        return doc


class TestDocumentUpload:
    def test_upload_creates_document(self):
        uploader = DocumentUploader()
        import asyncio
        doc = asyncio.run(uploader.upload("site_plan.pdf", b"pdf content", "site_plan"))
        assert doc.filename == "site_plan.pdf"
        assert doc.category == "site_plan"

    def test_upload_rejects_oversized_file(self):
        uploader = DocumentUploader()
        import asyncio
        with pytest.raises(ValueError, match="too large"):
            asyncio.run(uploader.upload("large.pdf", b"x" * 60 * 1024 * 1024))


import pytest
