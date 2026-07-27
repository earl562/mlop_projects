from __future__ import annotations

from plotlot.storage.records import DurableRecord, validate_bundle


def test_bundle_requires_one_tenant_and_host_engine_link() -> None:
    records = (
        DurableRecord("tenant-a", "event", "event-1"),
        DurableRecord("tenant-a", "raw_snapshot", "snapshot-1"),
        DurableRecord("tenant-a", "host_engine_link", "link-1"),
        DurableRecord("tenant-a", "report", "report-1"),
    )

    assert validate_bundle(records) == "tenant-a"
