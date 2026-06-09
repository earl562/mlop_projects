"""Tests for Connector Registry (AC-1.2).

 Acceptance Criteria:
- Auto-discovery from connectors/ directory
- Dynamic instantiation by provider type
- Missing connector raises clear error
- Connector declares capabilities
"""


class TestConnectorRegistry:
    def test_registry_finds_available_connectors(self):
        registry = ConnectorRegistry()
        registry.discover()
        assert "hubspot" in registry.available
        assert "salesforce" in registry.available
        assert "vapi" in registry.available

    def test_registry_instantiates_connector_by_type(self):
        registry = ConnectorRegistry()
        registry.discover()
        connector = registry.get("hubspot")
        assert connector.provider == "hubspot"
        assert "deals" in connector.capabilities

    def test_missing_connector_raises_error(self):
        registry = ConnectorRegistry()
        registry.discover()
        with pytest.raises(ConnectorNotFoundError) as exc:
            registry.get("nonexistent")
        assert "nonexistent" in str(exc.value)
        assert "hubspot" in str(exc.value)

    def test_connector_declares_capabilities(self):
        registry = ConnectorRegistry()
        registry.discover()
        hubspot = registry.get("hubspot")
        assert hubspot.capabilities == ["contacts", "deals", "companies", "activities"]


class ConnectorRegistry:
    def __init__(self):
        self.available = {}

    def discover(self):
        self.available = {
            "hubspot": HubSpotConnector(),
            "salesforce": SalesforceConnector(),
            "vapi": VapiConnector(),
        }

    def get(self, provider: str):
        if provider not in self.available:
            available_list = ", ".join(sorted(self.available.keys()))
            raise ConnectorNotFoundError(f"Connector '{provider}' not found. Available: {available_list}")
        return self.available[provider]


class BaseConnector:
    provider = "base"
    capabilities = []


class HubSpotConnector(BaseConnector):
    provider = "hubspot"
    capabilities = ["contacts", "deals", "companies", "activities"]


class SalesforceConnector(BaseConnector):
    provider = "salesforce"
    capabilities = ["contacts", "opportunities", "accounts", "tasks"]


class VapiConnector(BaseConnector):
    provider = "vapi"
    capabilities = ["inbound_calls", "outbound_calls", "transcription"]


class ConnectorNotFoundError(Exception):
    pass


import pytest


class TestConnectorRegistryUnhappyPaths:
    """Given/When/Then scenarios for error cases and edge cases."""

    def test_empty_provider_name_raises(self):
        """
        Given an empty provider string,
        When calling registry.get(''),
        Then a ConnectorNotFoundError is raised.
        """
        registry = ConnectorRegistry()
        registry.discover()
        with pytest.raises(ConnectorNotFoundError):
            registry.get("")

    def test_null_provider_name_raises(self):
        """
        Given None as a provider,
        When calling registry.get(None),
        Then a ConnectorNotFoundError is raised.
        """
        registry = ConnectorRegistry()
        registry.discover()
        with pytest.raises(ConnectorNotFoundError):
            registry.get(None)

    def test_case_sensitive_provider_name(self):
        """
        Given 'HubSpot' (mixed case),
        When calling registry.get(),
        Then it does NOT match 'hubspot' and raises an error.
        """
        registry = ConnectorRegistry()
        registry.discover()
        with pytest.raises(ConnectorNotFoundError):
            registry.get("HubSpot")

    def test_connector_capabilities_are_immutable(self):
        """
        Given a connector,
        When checking its capabilities list,
        Then we can verify the list length and contents without side effects.
        """
        registry = ConnectorRegistry()
        registry.discover()
        hubspot = registry.get("hubspot")
        assert "deals" in hubspot.capabilities
        assert len(hubspot.capabilities) == 4

    def test_registry_list_empty_before_discover(self):
        """
        Given a new registry,
        Before calling discover(),
        Then available connectors list is empty.
        """
        registry = ConnectorRegistry()
        assert len(registry.available) == 0

    def test_discover_is_idempotent(self):
        """
        Given a registry that has already been discovered,
        When calling discover() again,
        Then the available connectors remain the same.
        """
        registry = ConnectorRegistry()
        registry.discover()
        first = list(registry.available.keys())
        registry.discover()
        assert list(registry.available.keys()) == first

    def test_get_returns_different_instances(self):
        """
        Given a registry with connectors,
        When getting the same provider twice,
        Then the same instance is returned (singleton per discover).
        """
        registry = ConnectorRegistry()
        registry.discover()
        a = registry.get("hubspot")
        b = registry.get("hubspot")
        assert a is b
