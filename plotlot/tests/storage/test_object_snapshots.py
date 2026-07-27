from __future__ import annotations

from datetime import UTC, datetime

import pytest

from plotlot.storage.object_snapshots import (
    ImmutableMemoryObjectStore,
    ObjectTamperedError,
    SnapshotMetadata,
)


def test_raw_snapshot_round_trips_with_provenance() -> None:
    store = ImmutableMemoryObjectStore()
    metadata = SnapshotMetadata(
        tenant_id="tenant-a",
        object_key="raw/source-a/parcel-1.json",
        source_uri="https://official.example/parcel/1",
        fetched_at=datetime(2026, 7, 27, tzinfo=UTC),
        encryption_key_id="kms/plotlot/tenant-a",
    )

    receipt = store.put_immutable(metadata, b'{"parcel":"1"}')

    restored = store.get_verified(receipt)
    assert restored == b'{"parcel":"1"}'
    assert receipt.tenant_id == "tenant-a"
    assert receipt.source_uri == metadata.source_uri


def test_altered_object_byte_is_rejected() -> None:
    store = ImmutableMemoryObjectStore()
    metadata = SnapshotMetadata(
        tenant_id="tenant-a",
        object_key="raw/source-a/parcel-1.json",
        source_uri="https://official.example/parcel/1",
        fetched_at=datetime(2026, 7, 27, tzinfo=UTC),
        encryption_key_id="kms/plotlot/tenant-a",
    )
    receipt = store.put_immutable(metadata, b"original")
    store.inject_tamper_for_test(metadata.tenant_id, metadata.object_key, b"originaM")

    with pytest.raises(ObjectTamperedError):
        store.get_verified(receipt)
