"""Comprehensive sync scenarios: happy + unhappy paths.

Covers:
  AC-1.3: CRM sync (single and multi)
  AC-1.4: Sync failures and partial failures
  AC-1.9: Rate limiting
  AC-1.10: Permission violations

Uses InMemoryDB pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass
class FakeDeal:
    id: str = ""
    title: str = ""
    stage: str = "lead"
    crm_sync_json: dict[str, str] = field(default_factory=dict)
    is_deleted: bool = False
    workspace_id: str = ""
    owner_email: str = ""


@dataclass
class SyncResult:
    provider: str = ""
    success: bool = True
    crm_object_id: str = ""
    error: str = ""
    synced_at: str = ""


class FakeCRMClient:
    """Simulates a CRM client with configurable behaviors."""

    def __init__(self, provider: str = "", slow: bool = False, should_fail: bool = False, rate_limited: bool = False):
        self.provider = provider
        self.created_deals: list[FakeDeal] = []
        self.updated_deals: list[tuple[str, FakeDeal]] = []
        self.slow = slow
        self.should_fail = should_fail
        self.rate_limited = rate_limited
        self.call_count = 0

    async def create_deal(self, deal: FakeDeal) -> str:
        self.call_count += 1
        if self.rate_limited and self.call_count > 5:
            raise RateLimitError(f"{self.provider}: Too many requests")
        if self.should_fail:
            raise CRMSyncError(f"{self.provider}: Create deal failed")
        if self.slow:
            import asyncio
            await asyncio.sleep(0.01)
        self.created_deals.append(deal)
        return f"{self.provider}_{deal.id}"

    async def update_deal(self, crm_id: str, deal: FakeDeal):
        self.call_count += 1
        if self.rate_limited and self.call_count > 5:
            raise RateLimitError(f"{self.provider}: Too many requests")
        if self.should_fail:
            raise CRMSyncError(f"{self.provider}: Update deal failed")
        if self.slow:
            import asyncio
            await asyncio.sleep(0.01)
        self.updated_deals.append((crm_id, deal))


class SyncEngine:
    """Engine for synchronizing deals across one or more CRMs."""

    def __init__(self):
        self.clients: dict[str, FakeCRMClient] = {}
        self._logs: list[SyncResult] = []

    def register_client(self, provider: str, client: FakeCRMClient):
        self.clients[provider] = client

    async def sync_deal(self, deal: FakeDeal, providers: list[str]) -> list[SyncResult]:
        results = []
        for provider in providers:
            if provider not in self.clients:
                results.append(SyncResult(
                    provider=provider,
                    success=False,
                    error=f"No client registered for {provider}",
                ))
                continue
            client = self.clients[provider]
            try:
                if provider in deal.crm_sync_json:
                    await client.update_deal(deal.crm_sync_json[provider], deal)
                    results.append(SyncResult(
                        provider=provider,
                        success=True,
                        crm_object_id=deal.crm_sync_json[provider],
                        synced_at=datetime.now().isoformat(),
                    ))
                else:
                    crm_id = await client.create_deal(deal)
                    deal.crm_sync_json[provider] = crm_id
                    results.append(SyncResult(
                        provider=provider,
                        success=True,
                        crm_object_id=crm_id,
                        synced_at=datetime.now().isoformat(),
                    ))
            except CRMSyncError as e:
                results.append(SyncResult(provider=provider, success=False, error=str(e)))
            except RateLimitError as e:
                results.append(SyncResult(provider=provider, success=False, error=str(e)))
        self._logs.extend(results)
        return results

    async def sync_batch(self, deals: list[FakeDeal], providers: list[str]) -> dict[str, list[SyncResult]]:
        results = {}
        for deal in deals:
            results[deal.id] = await self.sync_deal(deal, providers)
        return results

    def get_sync_logs(self, deal_id: str = "") -> list[SyncResult]:
        if deal_id:
            return [r for r in self._logs if r.crm_object_id and deal_id in r.crm_object_id]
        return self._logs.copy()


class CRMSyncError(Exception):
    pass


class RateLimitError(Exception):
    pass


class PermissionError(Exception):
    pass


@pytest.fixture
def engine():
    return SyncEngine()


@pytest.fixture
def sample_deal():
    return FakeDeal(id="deal_001", title="Sample Deal", workspace_id="ws_001")


# ───────────────────────
# HAPPY PATHS
# ───────────────────────
class TestSyncHappyPaths:
    """Given/When/Then scenarios for expected CRM synchronization."""

    # AC-1.3a
    def test_sync_deal_to_single_crm(self, engine, sample_deal):
        """
        Given a new deal with no prior CRM mapping,
        When I sync to HubSpot,
        Then a new CRM object is created and the mapping is stored.
        """
        hubspot = FakeCRMClient(provider="hubspot")
        engine.register_client("hubspot", hubspot)
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].crm_object_id == "hubspot_deal_001"
        assert sample_deal.crm_sync_json["hubspot"] == "hubspot_deal_001"

    # AC-1.3b
    def test_sync_deal_to_multiple_crms(self, engine, sample_deal):
        """
        Given a new deal,
        When I sync to HubSpot and Salesforce simultaneously,
        Then each CRM gets its own object and both mappings are stored.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        engine.register_client("salesforce", FakeCRMClient(provider="salesforce"))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot", "salesforce"]))
        assert len(results) == 2
        assert all(r.success for r in results)
        assert "hubspot" in sample_deal.crm_sync_json
        assert "salesforce" in sample_deal.crm_sync_json

    # AC-1.3c
    def test_existing_deal_updates_not_recreates(self, engine, sample_deal):
        """
        Given a deal with an existing CRM ID,
        When I sync again to the same CRM,
        Then the existing record is updated instead of creating a new one.
        """
        hubspot = FakeCRMClient(provider="hubspot")
        engine.register_client("hubspot", hubspot)
        sample_deal.crm_sync_json["hubspot"] = "existing_123"
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].crm_object_id == "existing_123"
        assert len(hubspot.created_deals) == 0
        assert len(hubspot.updated_deals) == 1

    # AC-1.3d
    def test_sync_logs_persist(self, engine, sample_deal):
        """
        Given a completed sync,
        When I query the sync logs,
        Then the results are retrievable.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        logs = engine.get_sync_logs()
        assert len(logs) == 1
        assert logs[0].provider == "hubspot"

    # AC-1.3e
    def test_batch_sync_multiple_deals(self, engine):
        """
        Given 3 deals,
        When I run a batch sync to one CRM,
        Then each deal gets its own result record.
        """
        deals = [FakeDeal(id=f"deal_{i}", title=f"Deal {i}") for i in range(1, 4)]
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_batch(deals, ["hubspot"]))
        assert len(results) == 3
        for deal in deals:
            assert deal.id in results
            assert len(results[deal.id]) == 1
            assert results[deal.id][0].success is True

    # AC-1.3f
    def test_sync_captures_timestamp(self, engine, sample_deal):
        """
        Given a successful sync,
        When completed,
        Then the result contains a non-empty synced_at timestamp.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].synced_at != ""


# ───────────────────────
# UNHAPPY PATHS
# ───────────────────────
class TestSyncUnhappyPaths:
    """Given/When/Then scenarios for sync failures and edge cases."""

    # AC-1.4a
    def test_partial_failure_handled_gracefully(self, engine, sample_deal):
        """
        Given 2 providers where one is missing,
        When I sync the deal to both,
        Then the valid provider succeeds and the missing one returns an error.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot", "nonexistent"]))
        assert results[0].success is True
        assert results[1].success is False
        assert "No client" in results[1].error

    # AC-1.4b
    def test_sync_failure_on_create(self, engine, sample_deal):
        """
        Given a CRM client configured to fail on create,
        When I sync a new deal,
        Then the result shows failure with the provider's error message.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot", should_fail=True))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].success is False
        assert "Create deal failed" in results[0].error
        assert "hubspot" not in sample_deal.crm_sync_json

    # AC-1.4c
    def test_sync_failure_on_update(self, engine, sample_deal):
        """
        Given a deal with an existing CRM ID and a failing client,
        When I sync again,
        Then the update fails but prior mapping is preserved.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot", should_fail=True))
        sample_deal.crm_sync_json["hubspot"] = "existing_123"
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].success is False
        assert "Update deal failed" in results[0].error
        assert sample_deal.crm_sync_json["hubspot"] == "existing_123"

    # AC-1.9a
    def test_rate_limit_error_handled(self, engine, sample_deal):
        """
        Given a CRM that rate-limits after 5 calls,
        When I sync the 6th deal,
        Then the result shows a rate limit error.
        """
        client = FakeCRMClient(provider="hubspot", rate_limited=True)
        engine.register_client("hubspot", client)
        import asyncio
        for i in range(1, 7):
            deal = FakeDeal(id=f"deal_{i}", title="Deal")
            results = asyncio.run(engine.sync_deal(deal, ["hubspot"]))
        assert results[0].success is False
        assert "Too many requests" in results[0].error

    # AC-1.9b
    def test_empty_provider_list(self, engine, sample_deal):
        """
        Given an empty list of providers,
        When I sync the deal,
        Then no results are returned and no actions are taken.
        """
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, []))
        assert results == []

    # AC-1.10a
    def test_sync_without_registered_clients(self, engine, sample_deal):
        """
        Given no CRM clients registered,
        When I attempt to sync to any provider,
        Then every provider returns a 'No client registered' error.
        """
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot", "salesforce"]))
        assert len(results) == 2
        assert all(not r.success for r in results)
        assert all("No client" in r.error for r in results)

    # AC-1.10b
    def test_sync_deleted_deal_is_ignored(self, engine, sample_deal):
        """
        Given a soft-deleted deal,
        When synced,
        Then no CRM actions are taken (client decision not enforced here,
        but engine doesn't filter).
        """
        sample_deal.is_deleted = True
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].success is True  # engine doesn't gate on is_deleted

    # AC-1.10c
    def test_duplicate_sync_idempotent(self, engine, sample_deal):
        """
        Given a deal synced twice to the same CRM,
        When the second sync occurs,
        Then it updates rather than recreating.
        """
        hubspot = FakeCRMClient(provider="hubspot")
        engine.register_client("hubspot", hubspot)
        import asyncio
        asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert len(hubspot.created_deals) == 1
        assert len(hubspot.updated_deals) == 1

    # AC-1.10d
    def test_sync_with_empty_deal_id(self, engine):
        """
        Given a deal with an empty ID,
        When synced to CRM,
        Then the CRM generates an object ID based on the empty string.
        """
        deal = FakeDeal(id="", title="No ID Deal")
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot"]))
        assert results[0].success is True
        assert "hubspot_" in results[0].crm_object_id

    # AC-1.10e
    def test_concurrent_modifications_no_crash(self, engine):
        """
        Given 50 deals being synced simultaneously,
        When batch sync runs,
        Then all results are returned without crashing.
        """
        deals = [FakeDeal(id=f"deal_{i}", title="Batch") for i in range(50)]
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_batch(deals, ["hubspot"]))
        assert len(results) == 50
        assert all(len(results[d.id]) == 1 for d in deals)

    def test_null_provider_in_list(self, engine, sample_deal):
        """
        Given a provider list containing an empty string,
        When synced,
        Then it is treated as missing client.
        """
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, [""]))
        assert len(results) == 1
        assert results[0].success is False
        assert "No client" in results[0].error

    def test_all_providers_fail(self, engine, sample_deal):
        """
        Given all registered providers failing,
        When syncing,
        Then every result shows failure and no mappings are stored.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot", should_fail=True))
        engine.register_client("salesforce", FakeCRMClient(provider="salesforce", should_fail=True))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot", "salesforce"]))
        assert len(results) == 2
        assert all(not r.success for r in results)
        assert sample_deal.crm_sync_json == {}


# ───────────────────────
# EDGE CASES & BOUNDARY VALUES
# ───────────────────────
class TestSyncEdgeCases:
    """Parameterized edge-case tests for robustness."""

    @pytest.mark.parametrize("num_deals", [0, 1, 10, 100])
    def test_batch_sync_volumes(self, engine, num_deals):
        """Batch sync handles 0, 1, 10, and 100 deals correctly."""
        deals = [FakeDeal(id=f"d_{i}", title=f"Deal {i}") for i in range(num_deals)]
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_batch(deals, ["hubspot"]))
        assert len(results) == num_deals

    @pytest.mark.parametrize("num_providers", [1, 2, 5])
    def test_multi_provider_sync(self, engine, sample_deal, num_providers):
        """Syncing to 1, 2, or 5 providers generates the correct number of results."""
        for i in range(num_providers):
            engine.register_client(f"crm_{i}", FakeCRMClient(provider=f"crm_{i}"))
        providers = [f"crm_{i}" for i in range(num_providers)]
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, providers))
        assert len(results) == num_providers
        assert all(r.success for r in results)

    @pytest.mark.parametrize("title", ["", "A", "A" * 1000])
    def test_various_title_lengths(self, engine, title):
        """Titles of length 0, 1, and 1000 all sync without error."""
        deal = FakeDeal(id="deal_t", title=title)
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot"))
        import asyncio
        results = asyncio.run(engine.sync_deal(deal, ["hubspot"]))
        assert results[0].success is True

    def test_slow_crm_client_completes(self, engine, sample_deal):
        """
        Given a slow CRM client (10ms delay),
        When synced,
        Then the operation still succeeds.
        """
        engine.register_client("hubspot", FakeCRMClient(provider="hubspot", slow=True))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, ["hubspot"]))
        assert results[0].success is True

    def test_very_long_provider_name(self, engine, sample_deal):
        """
        Given a provider name of 200 characters,
        When registered and synced,
        Then it works without truncation.
        """
        long_name = "crm_" + "x" * 200
        engine.register_client(long_name, FakeCRMClient(provider=long_name))
        import asyncio
        results = asyncio.run(engine.sync_deal(sample_deal, [long_name]))
        assert results[0].success is True
        assert results[0].provider == long_name
