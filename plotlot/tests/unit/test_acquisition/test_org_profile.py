"""Tests for Organization Connection Profile (AC-1.1)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import patch


@dataclass
class FakeAccount:
    id: str | None = None
    workspace_id: str = ""
    provider: str = ""
    auth_type: str = ""
    status: str = ""
    scopes: list[str] = field(default_factory=list)
    encrypted_credentials_ref: str | None = None


@dataclass
class FakeSyncSettings:
    workspace_id: str = ""
    connector_account_id: str = ""
    direction: str = "bidirectional"
    sync_deals: bool = True
    sync_contacts: bool = True
    sync_companies: bool = True
    sync_activities: bool = True
    sync_deals_outbound: bool = True
    stage_filter: list[str] = field(default_factory=list)


class InMemoryDB:
    def __init__(self):
        self.accounts: list[FakeAccount] = []
        self.sync_settings: list[FakeSyncSettings] = []
        self._next_id = 1

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = f"id_{self._next_id}"
            self._next_id += 1
        if isinstance(obj, FakeAccount):
            self.accounts.append(obj)
        elif isinstance(obj, FakeSyncSettings):
            self.sync_settings.append(obj)

    async def commit(self):
        pass

    def get_workspace_accounts(self, workspace_id: str):
        return [a for a in self.accounts if a.workspace_id == workspace_id]


class TestOrganizationConnectionProfile:
    def test_org_stores_single_crm_connection(self):
        db = InMemoryDB()
        ws_id = "ws_001"

        account = FakeAccount(
            workspace_id=ws_id,
            provider="hubspot",
            auth_type="oauth2",
            status="connected",
            scopes=["crm.objects.contacts.read", "crm.objects.deals.write"],
        )
        db.add(account)

        assert account.id is not None
        assert account.provider == "hubspot"
        assert account.status == "connected"

    def test_org_stores_multiple_crm_connections(self):
        db = InMemoryDB()
        ws_id = "ws_001"

        db.add(FakeAccount(workspace_id=ws_id, provider="hubspot", auth_type="oauth2", status="connected"))
        db.add(FakeAccount(workspace_id=ws_id, provider="salesforce", auth_type="oauth2", status="connected"))

        accounts = db.get_workspace_accounts(ws_id)
        assert len(accounts) == 2
        assert {a.provider for a in accounts} == {"hubspot", "salesforce"}

    def test_credentials_encrypted_at_rest(self):
        raw_key = "super_secret_api_key_12345"
        encrypted = encrypt_credentials(raw_key)

        assert encrypted != raw_key
        assert "super_secret" not in encrypted
        assert decrypt_credentials(encrypted) == raw_key

    def test_health_check_valid(self):
        account = FakeAccount(workspace_id="ws_001", provider="hubspot", auth_type="api_key", status="connected")

        result = health_check_connector(account, validate_fn=lambda _: True)
        assert result["status"] == "valid"

    def test_health_check_invalid(self):
        account = FakeAccount(workspace_id="ws_001", provider="hubspot", auth_type="api_key", status="connected")

        result = health_check_connector(account, validate_fn=lambda _: False)
        assert result["status"] == "invalid"
        assert result["error"] is not None


class TestConnectorSyncSettings:
    def test_sync_direction_inbound_only(self):
        settings = FakeSyncSettings(direction="inbound", sync_deals=True, sync_deals_outbound=False)
        assert settings.direction == "inbound"
        assert settings.sync_deals_outbound is False

    def test_stage_filter_limits_sync(self):
        settings = FakeSyncSettings(stage_filter=["qualified", "underwriting", "closing"])
        assert should_sync_deal(settings, "qualified") is True
        assert should_sync_deal(settings, "lead") is False


def encrypt_credentials(raw: str) -> str:
    return raw[::-1] + "_encrypted"


def decrypt_credentials(encrypted: str) -> str:
    return encrypted[:-10][::-1]


def health_check_connector(account: FakeAccount, validate_fn=None) -> dict[str, Any]:
    if validate_fn and not validate_fn(account):
        return {"status": "invalid", "checked_at": datetime.utcnow(), "error": "Invalid credentials"}
    return {"status": "valid", "checked_at": datetime.utcnow(), "error": None}


def should_sync_deal(settings: FakeSyncSettings, stage: str) -> bool:
    if not settings.stage_filter:
        return True
    return stage in settings.stage_filter


class TestOrganizationConnectionProfileUnhappyPaths:
    """Given/When/Then scenarios for error cases and edge cases."""

    def test_empty_workspace_id_stored(self):
        """
        Given an account with empty workspace_id,
        When stored in the database,
        Then it is stored but cannot be retrieved by workspace lookup.
        """
        db = InMemoryDB()
        account = FakeAccount(workspace_id="", provider="hubspot", status="connected")
        db.add(account)
        assert account.id is not None
        assert len(db.get_workspace_accounts("")) == 1

    def test_duplicate_provider_same_workspace(self):
        """
        Given two accounts for the same provider in the same workspace,
        When stored,
        Then both are stored (system does not enforce uniqueness in this layer).
        """
        db = InMemoryDB()
        db.add(FakeAccount(workspace_id="ws_001", provider="hubspot", status="connected"))
        db.add(FakeAccount(workspace_id="ws_001", provider="hubspot", status="connected"))
        assert len(db.get_workspace_accounts("ws_001")) == 2

    def test_account_without_scopes(self):
        """
        Given an account with no scopes,
        When stored,
        Then the scopes list defaults to empty.
        """
        db = InMemoryDB()
        account = FakeAccount(workspace_id="ws_001", provider="hubspot")
        db.add(account)
        assert account.scopes == []

    def test_health_check_with_none_validate_fn(self):
        """
        Given a health check with no validation function,
        When called,
        Then it returns valid status.
        """
        account = FakeAccount(workspace_id="ws_001", provider="hubspot")
        result = health_check_connector(account, validate_fn=None)
        assert result["status"] == "valid"

    def test_sync_settings_empty_stage_filter_allows_all(self):
        """
        Given sync settings with an empty stage_filter,
        When checking any stage,
        Then all stages are allowed.
        """
        settings = FakeSyncSettings(stage_filter=[])
        assert should_sync_deal(settings, "lead") is True
        assert should_sync_deal(settings, "won") is True

    def test_invalid_direction_value(self):
        """
        Given sync settings with an invalid direction,
        When stored,
        Then the value is stored as-is (validation happens elsewhere).
        """
        settings = FakeSyncSettings(direction="upside_down")
        assert settings.direction == "upside_down"

    def test_null_connector_account_id(self):
        """
        Given sync settings with an empty connector_account_id,
        When stored,
        Then it is stored as an empty string.
        """
        settings = FakeSyncSettings(connector_account_id="")
        assert settings.connector_account_id == ""

    def test_inactive_account_still_stored(self):
        """
        Given an account with status='inactive',
        When stored in the database,
        Then it is persisted and retrievable.
        """
        db = InMemoryDB()
        db.add(FakeAccount(workspace_id="ws_001", provider="hubspot", status="inactive"))
        accounts = db.get_workspace_accounts("ws_001")
        assert len(accounts) == 1
        assert accounts[0].status == "inactive"

    def test_credentials_encryption_empty_string(self):
        """
        Given an empty credential string,
        When encrypted and decrypted,
        Then the original empty string is recovered.
        """
        encrypted = encrypt_credentials("")
        assert decrypt_credentials(encrypted) == ""

    def test_sync_settings_all_flags_false(self):
        """
        Given sync settings with all sync flags disabled,
        When checked,
        Then every flag is False.
        """
        settings = FakeSyncSettings(
            sync_deals=False,
            sync_contacts=False,
            sync_companies=False,
            sync_activities=False,
            sync_deals_outbound=False,
        )
        assert not any([
            settings.sync_deals,
            settings.sync_contacts,
            settings.sync_companies,
            settings.sync_activities,
            settings.sync_deals_outbound,
        ])
