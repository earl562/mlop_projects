"""Tests for data quality validation in the ingestion pipeline."""

from dataclasses import dataclass

from plotlot.ingestion.embedder import EMBEDDING_DIM
from plotlot.pipeline.ingest import validate_chunks


@dataclass
class FakeChunkMetadata:
    municipality: str = "Test City"
    county: str = "Test County"
    chapter: str = "Ch 1"
    section: str = "1.1"
    section_title: str = "General"
    zone_codes: list = None
    chunk_index: int = 0
    municode_node_id: str = "123"


@dataclass
class FakeChunk:
    text: str = "A" * 100
    metadata: FakeChunkMetadata = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = FakeChunkMetadata()


def _good_embedding():
    return [0.1] * EMBEDDING_DIM


class TestValidateChunks:
    def test_valid_chunks_pass(self):
        """Good chunks and embeddings pass validation."""
        chunks = [FakeChunk(), FakeChunk()]
        embeddings = [_good_embedding(), _good_embedding()]
        valid_c, valid_e = validate_chunks(chunks, embeddings)
        assert len(valid_c) == 2
        assert len(valid_e) == 2

    def test_zero_vector_filtered(self):
        """Zero-vector embeddings are filtered out."""
        chunks = [FakeChunk(), FakeChunk()]
        embeddings = [_good_embedding(), [0.0] * EMBEDDING_DIM]
        valid_c, valid_e = validate_chunks(chunks, embeddings)
        assert len(valid_c) == 1
        assert len(valid_e) == 1

    def test_wrong_dimension_filtered(self):
        """Embeddings with wrong dimension are filtered out."""
        chunks = [FakeChunk(), FakeChunk()]
        embeddings = [_good_embedding(), [0.1] * 512]
        valid_c, valid_e = validate_chunks(chunks, embeddings)
        assert len(valid_c) == 1

    def test_short_text_filtered(self):
        """Chunks with text shorter than threshold are filtered out."""
        chunks = [FakeChunk(), FakeChunk(text="too short")]
        embeddings = [_good_embedding(), _good_embedding()]
        valid_c, valid_e = validate_chunks(chunks, embeddings)
        assert len(valid_c) == 1

    def test_all_invalid_returns_empty(self):
        """All invalid chunks → empty result."""
        chunks = [FakeChunk(text="x")]
        embeddings = [[0.0] * EMBEDDING_DIM]
        valid_c, valid_e = validate_chunks(chunks, embeddings)
        assert len(valid_c) == 0
        assert len(valid_e) == 0
