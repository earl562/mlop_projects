"""Tests for CRM Sync Engine (AC-1.3)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeDeal:
    id: str = ""
    title: str = ""
    crm_sync_json: dict[str, str] = field(default_factory=dict)


@dataclass
class SyncResult:
    success: bool = True
    crm_object_id: str = ""
    error: str = ""


class FakeHubSpotClient:
    def __init__(self):
        self.created_deals = []
        self.updated_deals = []

    async def create_deal(self, deal: FakeDeal) -> str:
        self.created_deals.append(deal)
        return f"hubspot_{deal.id}"

    async def update_deal(self, crm_id: str, deal: FakeDeal):
        self.updated_deals.append((crm_id, deal))


class SyncEngine:
    def __init__(self):
        self.clients = {}

    def register_client(self, provider: str, client):
        self.clients[provider] = client

    async def sync_deal(self, deal: FakeDeal, providers: list[str]) -> list[SyncResult]:
        results = []
        for provider in providers:
            if provider not in self.clients:
                results.append(SyncResult(success=False, error=f"No client for {provider}"))
                continue
            client = self.clients[provider]
            if provider in deal.crm_sync_json:
                await client.update_deal(deal.crm_sync_json[provider], deal)
                results.append(SyncResult(success=True, crm_object_id=deal.crm_sync_json[provider]))
            else:
                crm_id = await client.create_deal(deal)
                deal.crm_sync_json[provider] = crm_id
                results.append(SyncResult(success=True, crm_object_id=crm_id))
        return results


class TestCRMSyncEngine:
    def test_deal_syncs_to_single_crm(self):
        engine = SyncEngine()
        hubspot = FakeHubSpotClient()
        engine.register_client("hubspot", hubspot)

        deal = FakeDeal(id="deal_001", title="Test Deal")
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot"]))

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].crm_object_id == "hubspot_deal_001"
        assert deal.crm_sync_json["hubspot"] == "hubspot_deal_001"

    def test_deal_syncs_to_multiple_crms(self):
        engine = SyncEngine()
        engine.register_client("hubspot", FakeHubSpotClient())
        engine.register_client("salesforce", FakeHubSpotClient())

        deal = FakeDeal(id="deal_002", title="Multi CRM Deal")
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot", "salesforce"]))

        assert len(results) == 2
        assert all(r.success for r in results)
        assert "hubspot" in deal.crm_sync_json
        assert "salesforce" in deal.crm_sync_json

    def test_existing_deal_updates_not_recreates(self):
        engine = SyncEngine()
        hubspot = FakeHubSpotClient()
        engine.register_client("hubspot", hubspot)

        deal = FakeDeal(id="deal_003", title="Updated Deal", crm_sync_json={"hubspot": "existing_123"})
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot"]))

        assert results[0].crm_object_id == "existing_123"
        assert len(hubspot.created_deals) == 0
        assert len(hubspot.updated_deals) == 1

    def test_partial_failure_handled_gracefully(self):
        engine = SyncEngine()
        engine.register_client("hubspot", FakeHubSpotClient())

        deal = FakeDeal(id="deal_004", title="Partial Deal")
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot", "nonexistent"]))

        assert results[0].success is True
        assert results[1].success is False
        assert "No client" in results[1].error
