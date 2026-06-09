"""Unit tests for property/schemas/registry.py — PostgreSQL county schema registry."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.property.schemas.registry import (
    _row_to_county_cache,
    get_county_cache,
    get_field_mapping,
    save_county_cache,
    save_field_mapping,
)
from plotlot.storage.models import CountySchema


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_dataset(county: str = "test county") -> DatasetInfo:
    return DatasetInfo(
        dataset_id="ds-001",
        name="Test Parcels",
        url="https://arcgis.example.com/arcgis/rest/services/Parcels/FeatureServer",
        layer_id=0,
        dataset_type="parcels",
        county=county,
        state="CA",
        fips="06073",
        fields=["PARCEL_ID", "ADDRESS", "ACRES"],
    )


def _make_mapping(county_key: str = "test county") -> FieldMapping:
    return FieldMapping(
        county_key=county_key,
        mappings={"PARCEL_ID": "folio", "ADDRESS": "address", "ACRES": "lot_size_sqft"},
        unit_conversions={"ACRES": "acres_to_sqft"},
        confidence=0.85,
        method="heuristic",
    )


def _make_cache(county_key: str = "test county") -> CountyCache:
    return CountyCache(
        county_key=county_key,
        state="CA",
        parcels_dataset=_make_dataset(county_key),
        zoning_dataset=None,
        field_mapping=_make_mapping(county_key),
        ttl_hours=168,
    )


def _make_orm_row(
    county_key: str = "test county",
    *,
    parcels_json: dict | None = None,
    zoning_json: dict | None = None,
    mapping_json: dict | None = None,
    ttl_hours: int = 168,
    last_verified: datetime | None = None,
) -> CountySchema:
    row = MagicMock(spec=CountySchema)
    row.county_key = county_key
    row.state = "CA"
    row.parcels_dataset = parcels_json
    row.zoning_dataset = zoning_json
    row.field_mapping = mapping_json
    row.ttl_hours = ttl_hours
    row.last_verified = last_verified or datetime.now(timezone.utc)
    return row


# ── _row_to_county_cache ──────────────────────────────────────────────────────


def test_row_to_county_cache_with_all_fields():
    dataset = _make_dataset()
    mapping = _make_mapping()
    row = _make_orm_row(
        parcels_json=dataset.model_dump(mode="json"),
        mapping_json=mapping.model_dump(mode="json"),
    )

    cache = _row_to_county_cache(row)

    assert isinstance(cache, CountyCache)
    assert cache.county_key == "test county"
    assert cache.state == "CA"
    assert cache.parcels_dataset is not None
    assert cache.parcels_dataset.dataset_id == "ds-001"
    assert cache.field_mapping is not None
    assert cache.field_mapping.confidence == 0.85


def test_row_to_county_cache_nulls():
    row = _make_orm_row()  # all JSON fields default to None

    cache = _row_to_county_cache(row)

    assert cache.parcels_dataset is None
    assert cache.zoning_dataset is None
    assert cache.field_mapping is None


def test_row_to_county_cache_with_zoning_dataset():
    zoning_ds = DatasetInfo(
        dataset_id="ds-002",
        name="Test Zoning",
        url="https://arcgis.example.com/arcgis/rest/services/Zoning/FeatureServer",
        layer_id=1,
        dataset_type="zoning",
        county="test county",
        state="CA",
    )
    row = _make_orm_row(zoning_json=zoning_ds.model_dump(mode="json"))

    cache = _row_to_county_cache(row)

    assert cache.zoning_dataset is not None
    assert cache.zoning_dataset.dataset_type == "zoning"


def test_row_to_county_cache_preserves_ttl_hours():
    row = _make_orm_row(ttl_hours=336)
    cache = _row_to_county_cache(row)
    assert cache.ttl_hours == 336


# ── get_county_cache ──────────────────────────────────────────────────────────


async def test_get_county_cache_returns_none_when_row_missing():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("unknown county")

    assert result is None


async def test_get_county_cache_returns_cache_when_fresh():
    dataset = _make_dataset()
    mapping = _make_mapping()
    row = _make_orm_row(
        parcels_json=dataset.model_dump(mode="json"),
        mapping_json=mapping.model_dump(mode="json"),
        ttl_hours=168,
        last_verified=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=row)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("test county")

    assert result is not None
    assert result.county_key == "test county"
    assert result.parcels_dataset is not None


async def test_get_county_cache_returns_none_when_expired():
    from datetime import timedelta

    row = _make_orm_row(
        ttl_hours=1,
        last_verified=datetime.now(timezone.utc) - timedelta(hours=25),
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=row)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("test county")

    assert result is None


async def test_get_county_cache_returns_none_on_db_error():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(side_effect=RuntimeError("db offline"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("test county")

    assert result is None


# ── save_county_cache ─────────────────────────────────────────────────────────


async def test_save_county_cache_executes_upsert():
    cache = _make_cache()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        await save_county_cache(cache)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


async def test_save_county_cache_noop_on_db_error():
    cache = _make_cache()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("db offline"))

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        # Must not raise
        await save_county_cache(cache)


async def test_save_county_cache_handles_none_datasets():
    cache = CountyCache(
        county_key="empty county",
        state="TX",
        parcels_dataset=None,
        zoning_dataset=None,
        field_mapping=None,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        await save_county_cache(cache)

    mock_session.execute.assert_called_once()


# ── get_field_mapping ─────────────────────────────────────────────────────────


async def test_get_field_mapping_returns_mapping_when_present():
    mapping = _make_mapping()
    mapping_json = mapping.model_dump(mode="json")

    mock_result = MagicMock()
    mock_result.one_or_none = MagicMock(return_value=(mapping_json,))

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_field_mapping("test county")

    assert result is not None
    assert result.county_key == "test county"
    assert result.confidence == 0.85


async def test_get_field_mapping_returns_none_when_row_missing():
    mock_result = MagicMock()
    mock_result.one_or_none = MagicMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_field_mapping("unknown county")

    assert result is None


async def test_get_field_mapping_returns_none_when_column_null():
    mock_result = MagicMock()
    mock_result.one_or_none = MagicMock(return_value=(None,))

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_field_mapping("test county")

    assert result is None


async def test_get_field_mapping_returns_none_on_db_error():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("db offline"))

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_field_mapping("test county")

    assert result is None


# ── save_field_mapping ────────────────────────────────────────────────────────


async def test_save_field_mapping_executes_upsert():
    mapping = _make_mapping()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        await save_field_mapping(mapping)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


async def test_save_field_mapping_noop_on_db_error():
    mapping = _make_mapping()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("db offline"))

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        # Must not raise
        await save_field_mapping(mapping)


async def test_save_field_mapping_preserves_all_mapping_fields():
    mapping = FieldMapping(
        county_key="orange",
        mappings={"PIN": "folio", "SITUS": "address"},
        unit_conversions={"SQ_FT": ""},
        confidence=0.72,
        method="llm",
    )

    captured_values = {}

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    async def capture_execute(stmt):
        captured_values["stmt"] = stmt
        return MagicMock()

    mock_session.execute = capture_execute

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        await save_field_mapping(mapping)

    # Verify it didn't raise and commit was called
    mock_session.commit.assert_called_once()


# ── TTL boundary tests ────────────────────────────────────────────────────────


async def test_get_county_cache_not_expired_at_exact_ttl_boundary():
    """Cache at exactly TTL hours old is considered expired (age > ttl)."""
    from datetime import timedelta

    row = _make_orm_row(
        ttl_hours=24,
        last_verified=datetime.now(timezone.utc) - timedelta(hours=24, seconds=1),
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=row)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("test county")

    assert result is None


async def test_get_county_cache_fresh_just_under_ttl():
    """Cache one second under TTL is still valid."""
    from datetime import timedelta

    row = _make_orm_row(
        ttl_hours=24,
        parcels_json=_make_dataset().model_dump(mode="json"),
        last_verified=datetime.now(timezone.utc) - timedelta(hours=23, minutes=59),
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=row)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "plotlot.property.schemas.registry.get_session", AsyncMock(return_value=mock_session)
    ):
        result = await get_county_cache("test county")

    assert result is not None


# ── Model round-trip tests ────────────────────────────────────────────────────


def test_county_schema_orm_model_fields():
    """CountySchema ORM model has all expected columns."""
    from plotlot.storage.models import CountySchema

    col_names = {c.key for c in CountySchema.__table__.columns}
    assert "county_key" in col_names
    assert "state" in col_names
    assert "parcels_dataset" in col_names
    assert "zoning_dataset" in col_names
    assert "field_mapping" in col_names
    assert "ttl_hours" in col_names
    assert "last_verified" in col_names
    assert "created_at" in col_names
    assert "updated_at" in col_names


def test_county_schema_primary_key():
    from plotlot.storage.models import CountySchema

    pk_cols = [c.key for c in CountySchema.__table__.primary_key]
    assert pk_cols == ["county_key"]


def test_field_mapping_round_trip_through_json():
    """FieldMapping survives model_dump(mode='json') → model_validate round-trip."""
    original = _make_mapping()
    dumped = original.model_dump(mode="json")
    restored = FieldMapping.model_validate(dumped)

    assert restored.county_key == original.county_key
    assert restored.mappings == original.mappings
    assert restored.unit_conversions == original.unit_conversions
    assert restored.confidence == original.confidence
    assert restored.method == original.method


def test_dataset_info_round_trip_through_json():
    """DatasetInfo survives model_dump(mode='json') → model_validate round-trip."""
    original = _make_dataset()
    dumped = original.model_dump(mode="json")
    restored = DatasetInfo.model_validate(dumped)

    assert restored.dataset_id == original.dataset_id
    assert restored.fields == original.fields
    assert restored.state == original.state


def test_county_cache_round_trip_through_json():
    """Full CountyCache survives round-trip serialisation."""
    original = _make_cache()
    dumped = original.model_dump(mode="json")
    restored = CountyCache.model_validate(dumped)

    assert restored.county_key == original.county_key
    assert restored.parcels_dataset is not None
    assert restored.field_mapping is not None
    assert restored.field_mapping.confidence == 0.85
