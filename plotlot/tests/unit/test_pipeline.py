"""Tests for the ingestion pipeline module."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from plotlot.core.types import (
    MUNICODE_CONFIGS,
    MunicodeConfig,
    NC_MUNICODE_CONFIGS,
    RawSection,
)
from plotlot.pipeline.ingest import (
    _resolve_all_configs,
    _resolve_config,
    _safe_log_metrics,
    _store_ordinance_sections,
    ingest_all,
    ingest_municipality,
)
from plotlot.storage.models import OrdinanceChunk, OrdinanceSection


class TestResolveConfig:
    @pytest.mark.asyncio
    async def test_resolve_from_discovery(self):
        discovered = MunicodeConfig(
            municipality="Coral Gables",
            county="miami_dade",
            client_id=100,
            product_id=200,
            job_id=300,
            zoning_node_id="CG",
        )

        async def mock_get_configs():
            return {"coral_gables": discovered}

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            config = await _resolve_config("coral_gables")

        assert config.municipality == "Coral Gables"

    @pytest.mark.asyncio
    async def test_resolve_fallback(self):
        async def mock_get_configs():
            raise ConnectionError("API down")

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            config = await _resolve_config("miami_dade")

        assert config.municipality == "Unincorporated Miami-Dade"

    @pytest.mark.asyncio
    async def test_resolve_unknown_raises(self):
        async def mock_get_configs():
            return {}

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            with pytest.raises(ValueError, match="Unknown municipality key"):
                await _resolve_config("nonexistent_city")

    @pytest.mark.asyncio
    async def test_resolve_live_discovery_with_state(self):
        """A warm-cache miss + state falls back to targeted single-name discovery
        (re-ingesting a county-batch city like Tiburon, not in the curated cache)."""
        discovered = MunicodeConfig(
            municipality="Tiburon",
            county="marin",
            client_id=9796,
            product_id=16657,
            job_id=475397,
            zoning_node_id="CH16ZO",
        )

        async def empty_cache():
            return {}

        with (
            patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=empty_cache),
            patch(
                "plotlot.ingestion.discovery.discover_municode_authority_for_name",
                new=AsyncMock(return_value=discovered),
            ) as mock_disc,
        ):
            config = await _resolve_config("tiburon", state="CA")

        assert config.municipality == "Tiburon"
        # Key was de-slugged to a proper jurisdiction name for the lookup.
        mock_disc.assert_awaited_once_with("Tiburon", "CA")

    @pytest.mark.asyncio
    async def test_resolve_non_municode_with_state_raises(self):
        """When live discovery finds nothing (non-Municode codifier, e.g. Sausalito),
        the error must say so rather than silently doing nothing."""

        async def empty_cache():
            return {}

        with (
            patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=empty_cache),
            patch(
                "plotlot.ingestion.discovery.discover_municode_authority_for_name",
                new=AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(ValueError, match="non-Municode codifier"):
                await _resolve_config("sausalito", state="CA")

    @pytest.mark.asyncio
    async def test_resolve_unknown_without_state_hints_state_flag(self):
        async def empty_cache():
            return {}

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=empty_cache):
            with pytest.raises(ValueError, match="--state"):
                await _resolve_config("tiburon")


class TestResolveAllConfigs:
    @pytest.mark.asyncio
    async def test_uses_discovery(self):
        discovered = {
            "coral_gables": MunicodeConfig(
                municipality="Coral Gables",
                county="miami_dade",
                client_id=100,
                product_id=200,
                job_id=300,
                zoning_node_id="CG",
            ),
        }

        async def mock_get_configs():
            return discovered

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            configs = await _resolve_all_configs()

        assert "coral_gables" in configs

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        async def mock_get_configs():
            raise ConnectionError("API down")

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            configs = await _resolve_all_configs()

        assert "miami_dade" in configs
        assert "fort_lauderdale" in configs


class TestIngestMunicipality:
    @pytest.mark.asyncio
    async def test_invalid_key_raises(self):
        async def mock_get_configs():
            return {}

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs
        ):
            with pytest.raises(ValueError, match="Unknown municipality key"):
                await ingest_municipality("nonexistent_city")

    def test_municode_configs_has_expected_keys(self):
        assert "miami_dade" in MUNICODE_CONFIGS
        assert "fort_lauderdale" in MUNICODE_CONFIGS

    def test_municode_config_fields(self):
        for key, config in MUNICODE_CONFIGS.items():
            assert config.municipality, f"{key} missing municipality"
            assert config.county, f"{key} missing county"
            assert config.client_id > 0, f"{key} invalid client_id"
            assert config.product_id > 0, f"{key} invalid product_id"
            assert config.job_id > 0, f"{key} invalid job_id"
            assert config.zoning_node_id, f"{key} missing zoning_node_id"

    @pytest.mark.asyncio
    async def test_ingest_empty_scrape(self):
        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])
            count = await ingest_municipality("miami_dade")

        assert count == 0

    @pytest.mark.asyncio
    async def test_ingest_full_pipeline(self):
        mock_section = RawSection(
            municipality="Unincorporated Miami-Dade",
            county="miami_dade",
            node_id="test_node",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33 - ZONING",
            html_content="<p>The minimum lot width for RU-1 is 75 feet. The minimum lot area is 7,500 square feet. The maximum building height is 35 feet.</p>",
            depth=2,
        )

        mock_embedding = [0.1] * 1024

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock),
            patch(
                "plotlot.pipeline.ingest.get_session", new_callable=AsyncMock
            ) as mock_get_session,
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [mock_embedding]

            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session

            count = await ingest_municipality("miami_dade")

        assert count == 1
        # Two execute calls now: chunks upsert + sections index upsert (Slice 3.1)
        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_rollback_on_error(self):
        mock_section = RawSection(
            municipality="Fort Lauderdale",
            county="broward",
            node_id="test",
            heading="Test Section",
            parent_heading=None,
            html_content="<p>Test content for rollback testing with enough characters to pass minimum.</p>",
            depth=1,
        )

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock),
            patch(
                "plotlot.pipeline.ingest.get_session", new_callable=AsyncMock
            ) as mock_get_session,
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [[0.1] * 1024]

            mock_session = AsyncMock()
            mock_session.commit.side_effect = Exception("DB error")
            mock_get_session.return_value = mock_session

            with pytest.raises(Exception, match="DB error"):
                await ingest_municipality("fort_lauderdale")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestIngestAll:
    @pytest.mark.asyncio
    async def test_ingest_all_uses_discovery(self):
        configs = {
            "test_city": MunicodeConfig(
                municipality="Test City",
                county="test",
                client_id=1,
                product_id=2,
                job_id=3,
                zoning_node_id="N",
            ),
        }

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
        ):
            mock_disc.return_value = configs
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])

            results = await ingest_all()

        assert isinstance(results, dict)
        assert "test_city" in results

    @pytest.mark.asyncio
    async def test_ingest_all_handles_failures(self):
        configs = {
            "good_city": MunicodeConfig(
                municipality="Good City",
                county="test",
                client_id=1,
                product_id=2,
                job_id=3,
                zoning_node_id="N",
            ),
            "bad_city": MunicodeConfig(
                municipality="Bad City",
                county="test",
                client_id=4,
                product_id=5,
                job_id=6,
                zoning_node_id="N2",
            ),
        }

        call_count = {"n": 0}

        async def mock_scrape(config):
            call_count["n"] += 1
            if config.municipality == "Bad City":
                raise ConnectionError("Scrape failed")
            return []

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_disc.return_value = configs
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(side_effect=mock_scrape)

            results = await ingest_all()

        assert mock_sleep.await_args_list == [call(30.0), call(0)]
        assert call_count["n"] == 3
        assert len(results) == 2
        assert results["good_city"] == 0
        assert results["bad_city"] == 0


class TestOrdinanceChunkLineageFields:
    """B2: Verify OrdinanceChunk model has lineage columns."""

    def test_has_source_url_column(self):
        cols = {c.name for c in OrdinanceChunk.__table__.columns}
        assert "source_url" in cols

    def test_has_scraped_at_column(self):
        cols = {c.name for c in OrdinanceChunk.__table__.columns}
        assert "scraped_at" in cols

    def test_has_embedding_model_column(self):
        cols = {c.name for c in OrdinanceChunk.__table__.columns}
        assert "embedding_model" in cols

    def test_lineage_columns_are_nullable(self):
        table = OrdinanceChunk.__table__
        assert table.c.source_url.nullable is True
        assert table.c.scraped_at.nullable is True
        assert table.c.embedding_model.nullable is True


class TestOrdinanceChunkStateField:
    """B6: Verify OrdinanceChunk model has state column."""

    def test_has_state_column(self):
        cols = {c.name for c in OrdinanceChunk.__table__.columns}
        assert "state" in cols

    def test_state_column_is_nullable(self):
        table = OrdinanceChunk.__table__
        assert table.c.state.nullable is True

    def test_state_column_max_length(self):
        col = OrdinanceChunk.__table__.c.state
        assert col.type.length == 2


class TestMunicodeConfigState:
    """B6: Verify MunicodeConfig has state field with correct defaults."""

    def test_fl_configs_default_to_fl(self):
        for key, config in MUNICODE_CONFIGS.items():
            assert config.state == "FL", f"{key} should default to FL"

    def test_nc_configs_set_to_nc(self):
        for key, config in NC_MUNICODE_CONFIGS.items():
            assert config.state == "NC", f"{key} should be NC"

    def test_default_state_is_fl(self):
        config = MunicodeConfig(
            municipality="Test",
            county="test",
            client_id=1,
            product_id=2,
            job_id=3,
            zoning_node_id="TEST",
        )
        assert config.state == "FL"


class TestSafeLogMetrics:
    """A7: _safe_log_metrics wraps log_metrics so MLflow errors never break ingestion."""

    def test_safe_log_metrics_calls_log_metrics(self):
        """_safe_log_metrics delegates to tracing.log_metrics."""
        with patch("plotlot.pipeline.ingest.log_metrics") as mock_log:
            _safe_log_metrics({"ingest.sections_scraped": 10})
            mock_log.assert_called_once_with({"ingest.sections_scraped": 10})

    def test_safe_log_metrics_swallows_errors(self):
        """MLflow failure must not propagate — pipeline keeps running."""
        with patch("plotlot.pipeline.ingest.log_metrics", side_effect=RuntimeError("MLflow down")):
            # Should NOT raise
            _safe_log_metrics({"ingest.sections_scraped": 10})

    def test_safe_log_metrics_swallows_connection_error(self):
        """Even connection-level errors are swallowed."""
        with patch(
            "plotlot.pipeline.ingest.log_metrics", side_effect=ConnectionError("no network")
        ):
            _safe_log_metrics({"ingest.chunks_stored": 5})


class TestIngestMunicipalityMLflowMetrics:
    """A7: Verify log_metrics is called at each pipeline stage during ingestion."""

    @pytest.mark.asyncio
    async def test_metrics_logged_during_full_pipeline(self):
        """Full pipeline run should log metrics at scrape, chunk, embed, validate, store."""
        mock_section = RawSection(
            municipality="Unincorporated Miami-Dade",
            county="miami_dade",
            node_id="test_node",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33 - ZONING",
            html_content=(
                "<p>The minimum lot width for RU-1 is 75 feet. "
                "The minimum lot area is 7,500 square feet. "
                "The maximum building height is 35 feet.</p>"
            ),
            depth=2,
        )

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock),
            patch(
                "plotlot.pipeline.ingest.get_session", new_callable=AsyncMock
            ) as mock_get_session,
            patch("plotlot.pipeline.ingest.log_metrics") as mock_log_metrics,
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [[0.1] * 1024]

            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session

            count = await ingest_municipality("miami_dade")

        assert count == 1

        # Collect all metric keys logged across all calls
        logged_keys = set()
        for c in mock_log_metrics.call_args_list:
            metrics_dict = c[0][0]
            logged_keys.update(metrics_dict.keys())

        # Each pipeline stage should have logged its metrics
        assert "ingest.sections_scraped" in logged_keys
        assert "ingest.chunks_created" in logged_keys
        assert "ingest.chunks_embedded" in logged_keys
        assert "ingest.chunks_valid" in logged_keys
        assert "ingest.chunks_filtered" in logged_keys
        assert "ingest.chunks_stored" in logged_keys

    @pytest.mark.asyncio
    async def test_metrics_logged_on_empty_scrape(self):
        """Empty scrape should still log sections_scraped=0."""
        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.log_metrics") as mock_log_metrics,
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])

            count = await ingest_municipality("miami_dade")

        assert count == 0
        # sections_scraped should still be logged even on empty result
        mock_log_metrics.assert_called_with({"ingest.sections_scraped": 0})

    @pytest.mark.asyncio
    async def test_mlflow_failure_does_not_break_pipeline(self):
        """If log_metrics raises, the pipeline should still complete successfully."""
        mock_section = RawSection(
            municipality="Unincorporated Miami-Dade",
            county="miami_dade",
            node_id="test_node",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33 - ZONING",
            html_content=(
                "<p>The minimum lot width for RU-1 is 75 feet. "
                "The minimum lot area is 7,500 square feet. "
                "The maximum building height is 35 feet.</p>"
            ),
            depth=2,
        )

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed,
            patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock),
            patch(
                "plotlot.pipeline.ingest.get_session", new_callable=AsyncMock
            ) as mock_get_session,
            patch(
                "plotlot.pipeline.ingest.log_metrics",
                side_effect=RuntimeError("MLflow crashed"),
            ),
        ):
            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [[0.1] * 1024]

            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session

            # Pipeline should complete despite MLflow being broken
            count = await ingest_municipality("miami_dade")

        assert count == 1
        # Two execute calls now: chunks upsert + sections index upsert (Slice 3.1)
        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2
        mock_session.close.assert_called_once()


class TestIngestAllMLflowMetrics:
    """A7: Verify ingest_all logs aggregate metrics."""

    @pytest.mark.asyncio
    async def test_ingest_all_logs_aggregate_metrics(self):
        """ingest_all should log total_chunks, municipalities_processed, municipalities_failed."""
        configs = {
            "test_city": MunicodeConfig(
                municipality="Test City",
                county="test",
                client_id=1,
                product_id=2,
                job_id=3,
                zoning_node_id="N",
            ),
        }

        with (
            patch(
                "plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock
            ) as mock_disc,
            patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper,
            patch("plotlot.pipeline.ingest.log_metrics") as mock_log_metrics,
        ):
            mock_disc.return_value = configs
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])

            results = await ingest_all()

        assert "test_city" in results

        # Find the ingest_all aggregate metrics call (last call with total_chunks)
        aggregate_calls = [
            c for c in mock_log_metrics.call_args_list if "ingest.total_chunks" in c[0][0]
        ]
        assert len(aggregate_calls) == 1
        agg_metrics = aggregate_calls[0][0][0]
        assert "ingest.total_chunks" in agg_metrics
        assert "ingest.municipalities_processed" in agg_metrics
        assert "ingest.municipalities_failed" in agg_metrics


class TestOrdinanceSectionModel:
    """Slice 3.1: OrdinanceSection is the structural index over chunks."""

    def test_has_structural_columns(self):
        cols = {c.name for c in OrdinanceSection.__table__.columns}
        # Path + cross_refs + referenced_by are the three structural fields.
        assert "path" in cols
        assert "cross_refs" in cols
        assert "referenced_by" in cols
        assert "section_type" in cols
        assert "section_number" in cols

    def test_natural_key_constraint(self):
        constrs = {c.name for c in OrdinanceSection.__table__.constraints}
        assert "uq_section_natural_key" in constrs

    def test_default_section_type_is_regulation(self):
        col = OrdinanceSection.__table__.c.section_type
        # server_default is the SQL-level default; the model default is "regulation"
        assert col.default.arg == "regulation"

    def test_referenced_by_defaults_empty(self):
        col = OrdinanceSection.__table__.c.referenced_by
        assert col.default.arg == []

    def test_path_and_cross_refs_are_string_arrays(self):
        # Both must be ARRAY(String) for pgvector/Postgres storage.
        from sqlalchemy.dialects.postgresql import ARRAY

        assert isinstance(OrdinanceSection.__table__.c.path.type, ARRAY)
        assert isinstance(OrdinanceSection.__table__.c.cross_refs.type, ARRAY)
        assert isinstance(OrdinanceSection.__table__.c.referenced_by.type, ARRAY)

    def test_has_lineage_columns(self):
        # Provenance mirrors OrdinanceChunk so freshness (3.4) / boundary
        # checks can resolve against the section, not just chunks.
        cols = {c.name for c in OrdinanceSection.__table__.columns}
        assert "source_url" in cols
        assert "scraped_at" in cols
        assert "state" in cols


class TestStoreOrdinanceSections:
    """Slice 3.1: ingest now indexes one OrdinanceSection per unique node_id."""

    @pytest.mark.asyncio
    async def test_upserts_one_row_per_unique_node(self):
        from plotlot.core.types import ChunkMetadata, TextChunk
        from plotlot.core.types import MunicodeConfig

        config = MunicodeConfig(
            municipality="Fort Lauderdale",
            county="broward",
            client_id=1,
            product_id=2,
            job_id=3,
            zoning_node_id="Z",
        )
        # Two chunks sharing one node_id -> ONE section row.
        meta = ChunkMetadata(
            municipality="Fort Lauderdale",
            county="broward",
            chapter="Chapter 47",
            section="Sec. 47-5.60",
            section_title="Schedule of District Regulations",
            zone_codes=["RS-8"],
            chunk_index=0,
            municode_node_id="NODE_A",
            path=["Chapter 47", "Sec. 47-5.60"],
            cross_refs=["47-24.3"],
            section_type="dimensional_table",
        )
        chunks = [
            TextChunk(text="part one", metadata=meta),
            TextChunk(text="part two", metadata=replace(meta, chunk_index=1)),
        ]

        with patch("plotlot.pipeline.ingest.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_insert.return_value = mock_stmt
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            session = AsyncMock()

            count = await _store_ordinance_sections(session, chunks, config)

        assert count == 1
        # pg_insert(Model) -> .values(row_dicts); row_dicts are on the .values call.
        mock_insert.assert_called_once_with(OrdinanceSection)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        row_dicts = mock_stmt.values.call_args[0][0]
        assert len(row_dicts) == 1
        row = row_dicts[0]
        assert row["node_id"] == "NODE_A"
        assert row["section_type"] == "dimensional_table"
        assert row["path"] == ["Chapter 47", "Sec. 47-5.60"]
        assert row["cross_refs"] == ["47-24.3"]
        # referenced_by is NOT set by the indexer (defaults to [] in the model /
        # DB) — the backfill owns it, so it's intentionally absent from row_dicts.
        assert "referenced_by" not in row
        # The conflict target must be the natural-key constraint (NOT a column
        # list) — referenced_by must NOT be in the update set (backfill owns it).
        conflict_call = mock_stmt.values.return_value.on_conflict_do_update.call_args
        assert conflict_call.kwargs.get("constraint") == "uq_section_natural_key"
        set_ = conflict_call.kwargs.get("set_", {})
        assert "referenced_by" not in set_

    @pytest.mark.asyncio
    async def test_skips_chunks_without_node_id(self):
        from plotlot.core.types import ChunkMetadata, TextChunk
        from plotlot.core.types import MunicodeConfig

        config = MunicodeConfig(
            municipality="San Diego",
            county="san_diego",
            client_id=1,
            product_id=2,
            job_id=3,
            zoning_node_id="Z",
        )
        meta = ChunkMetadata(
            municipality="San Diego",
            county="san_diego",
            chapter="Ch 11",
            section="Sec. 11",
            section_title="x",
            zone_codes=[],
            chunk_index=0,
            municode_node_id="",
            path=["Ch 11"],
            cross_refs=[],
            section_type="regulation",
        )
        chunks = [TextChunk(text="t", metadata=meta)]

        session = AsyncMock()
        count = await _store_ordinance_sections(session, chunks, config)
        assert count == 0
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_distinct_node_ids_produce_distinct_rows(self):
        from plotlot.core.types import ChunkMetadata, TextChunk
        from plotlot.core.types import MunicodeConfig

        config = MunicodeConfig(
            municipality="M",
            county="c",
            client_id=1,
            product_id=2,
            job_id=3,
            zoning_node_id="Z",
        )
        metas = [
            ChunkMetadata(
                municipality="M",
                county="c",
                chapter="Ch 47",
                section=f"Sec. 47-5.{i}",
                section_title="x",
                zone_codes=[],
                chunk_index=0,
                municode_node_id=f"NODE_{i}",
                path=["Ch 47"],
                cross_refs=[],
                section_type="regulation",
            )
            for i in range(3)
        ]
        chunks = [TextChunk(text=f"t{i}", metadata=m) for i, m in enumerate(metas)]

        with patch("plotlot.pipeline.ingest.pg_insert") as mock_insert:
            mock_stmt = MagicMock()
            mock_insert.return_value = mock_stmt
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            session = AsyncMock()

            count = await _store_ordinance_sections(session, chunks, config)

        assert count == 3
        row_dicts = mock_stmt.values.call_args[0][0]
        assert {r["node_id"] for r in row_dicts} == {"NODE_0", "NODE_1", "NODE_2"}
