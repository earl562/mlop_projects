"""Tests for the abstract PropertyProvider interface and registry.

Verifies:
  - Provider registration and lookup
  - County alias resolution
  - Registry-based delegation from lookup_property()
  - Each concrete provider delegates to the correct internal function
"""

import pytest
from unittest.mock import AsyncMock, patch

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.property.broward import BrowardProvider
from plotlot.property.miami_dade import MiamiDadeProvider
from plotlot.property.palm_beach import PalmBeachProvider
from plotlot.property.registry import (
    _PROVIDERS,
    get_provider,
    register_provider,
    registered_counties,
)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class TestPropertyProviderABC:
    def test_cannot_instantiate(self):
        """PropertyProvider is abstract — direct instantiation must fail."""
        with pytest.raises(TypeError):
            PropertyProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_lookup(self):
        """Subclass without ``lookup`` raises TypeError on instantiation."""

        class Incomplete(PropertyProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_subclass_with_lookup_works(self):
        """Concrete subclass that implements ``lookup`` can be instantiated."""

        class Complete(PropertyProvider):
            async def lookup(self, address, county, *, lat=None, lng=None):
                return None

        assert isinstance(Complete(), PropertyProvider)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_builtin_providers_registered(self):
        """All three FL counties are registered after package import."""
        counties = registered_counties()
        assert "miami-dade" in counties
        assert "miami dade" in counties
        assert "broward" in counties
        assert "palm beach" in counties

    def test_get_provider_case_insensitive(self):
        assert get_provider("Miami-Dade") is not None
        assert get_provider("BROWARD") is not None
        assert get_provider("Palm Beach") is not None

    def test_get_provider_unknown(self):
        assert get_provider("Monroe") is None
        assert get_provider("") is None

    def test_register_and_retrieve_custom(self):
        """Register a custom provider and retrieve it."""

        class FakeProvider(PropertyProvider):
            async def lookup(self, address, county, *, lat=None, lng=None):
                return PropertyRecord(folio="FAKE-001")

        provider = FakeProvider()
        register_provider("test-county", provider)
        try:
            assert get_provider("test-county") is provider
            assert "test-county" in registered_counties()
        finally:
            # Clean up so we don't pollute other tests
            _PROVIDERS.pop("test-county", None)

    def test_miami_dade_alias_same_instance(self):
        """'miami-dade' and 'miami dade' resolve to the same provider."""
        assert get_provider("miami-dade") is get_provider("miami dade")


# ---------------------------------------------------------------------------
# Concrete providers delegate correctly
# ---------------------------------------------------------------------------


class TestMiamiDadeProvider:
    @pytest.mark.asyncio
    async def test_delegates_to_lookup_miami_dade(self):
        mock_record = PropertyRecord(folio="MDC-001", county="Miami-Dade")
        provider = MiamiDadeProvider()

        with patch(
            "plotlot.property.miami_dade._lookup_miami_dade",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_fn:
            result = await provider.lookup("123 Main St", "Miami-Dade", lat=25.9, lng=-80.2)

        mock_fn.assert_awaited_once_with("123 Main St", 25.9, -80.2)
        assert result is mock_record


class TestBrowardProvider:
    @pytest.mark.asyncio
    async def test_delegates_to_lookup_broward(self):
        mock_record = PropertyRecord(folio="BROW-001", county="Broward")
        provider = BrowardProvider()

        with patch(
            "plotlot.property.broward._lookup_broward",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_fn:
            result = await provider.lookup("456 Oak Ave", "Broward", lat=26.1, lng=-80.1)

        mock_fn.assert_awaited_once_with("456 Oak Ave", 26.1, -80.1)
        assert result is mock_record


class TestPalmBeachProvider:
    @pytest.mark.asyncio
    async def test_delegates_to_lookup_palm_beach(self):
        mock_record = PropertyRecord(folio="PBC-001", county="Palm Beach")
        provider = PalmBeachProvider()

        with patch(
            "plotlot.property.palm_beach._lookup_palm_beach",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_fn:
            result = await provider.lookup("789 Elm St", "Palm Beach", lat=26.7, lng=-80.0)

        mock_fn.assert_awaited_once_with("789 Elm St", 26.7, -80.0)
        assert result is mock_record


# ---------------------------------------------------------------------------
# Top-level lookup_property (from plotlot.property)
# ---------------------------------------------------------------------------


class TestPropertyPackageLookup:
    @pytest.mark.asyncio
    async def test_routes_to_correct_provider(self):
        """plotlot.property.lookup_property delegates to the right provider."""
        from plotlot.property import lookup_property

        mock_record = PropertyRecord(folio="TEST-001", county="Broward")

        with patch(
            "plotlot.property.broward._lookup_broward",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            result = await lookup_property("100 Test Rd", "Broward", lat=26.0, lng=-80.0)

        assert result is not None
        assert result.folio == "TEST-001"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_county(self):
        from plotlot.property import lookup_property

        result = await lookup_property("123 Main St", "Monroe", lat=24.5, lng=-81.8)
        assert result is None

    @pytest.mark.asyncio
    async def test_catches_provider_exceptions(self):
        """Provider exceptions are caught and None is returned."""
        from plotlot.property import lookup_property

        with patch(
            "plotlot.property.miami_dade._lookup_miami_dade",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ArcGIS down"),
        ):
            result = await lookup_property(
                "171 NE 209th Ter", "Miami-Dade", lat=25.9, lng=-80.2,
            )

        assert result is None


# ---------------------------------------------------------------------------
# Backward compat: retrieval.property.lookup_property still works
# ---------------------------------------------------------------------------


class TestRetrievalBackwardCompat:
    @pytest.mark.asyncio
    async def test_retrieval_lookup_uses_registry(self):
        """The old import path delegates through the registry."""
        from plotlot.retrieval.property import lookup_property

        mock_record = PropertyRecord(folio="COMPAT-001", county="Miami-Dade")

        with patch(
            "plotlot.property.miami_dade._lookup_miami_dade",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            result = await lookup_property(
                "171 NE 209th Ter", "Miami-Dade", lat=25.9, lng=-80.2,
            )

        assert result is not None
        assert result.folio == "COMPAT-001"
