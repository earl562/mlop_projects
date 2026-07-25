"""Unit tests for development-permit signals (SD Accela) + chat surfacing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


from plotlot.core.types import PermitRecord
from plotlot.pipeline.permits import fetch_development_signals, fetch_sd_permits


def _mock_http(json_data: dict):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


def _permit_feature(holder: str, ptype: str, status: str, ts: int | None, title: str):
    return {
        "attributes": {
            "APPROVAL_PERMIT_HOLDER": holder,
            "APPROVAL_TYPE": ptype,
            "APPROVAL_STATUS": status,
            "APPROVAL_ISSUE_DATE": ts,
            "PROJECT_TITLE": title,
            "APPROVAL_URL": "https://example/permit",
        }
    }


class TestFetchSdPermits:
    async def test_parses_permits_and_epoch_ms_date(self):
        data = {
            "features": [
                _permit_feature("Belmont West", "Building", "Issued", 1_700_000_000_000, "MF-42"),
            ]
        }
        with patch("httpx.AsyncClient", return_value=_mock_http(data)):
            out = await fetch_sd_permits("4364230200")
        assert len(out) == 1
        assert isinstance(out[0], PermitRecord)
        assert out[0].permit_holder == "Belmont West"
        assert out[0].issue_date == "2023-11-14"  # epoch-ms → ISO date

    async def test_missing_date_is_blank(self):
        data = {"features": [_permit_feature("X", "Building", "Issued", None, "T")]}
        with patch("httpx.AsyncClient", return_value=_mock_http(data)):
            out = await fetch_sd_permits("123")
        assert out[0].issue_date == ""

    async def test_api_error_returns_empty(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=Exception("timeout"))
        with patch("httpx.AsyncClient", return_value=client):
            assert await fetch_sd_permits("123") == []


class TestDevelopmentSignals:
    async def test_aggregates_active_and_holders(self):
        permits = [
            PermitRecord(permit_holder="Belmont West", permit_status="Issued"),
            PermitRecord(permit_holder="HCI Systems", permit_status="Inspection Followup"),
            PermitRecord(permit_holder="Belmont West", permit_status="Completed"),
        ]
        with patch(
            "plotlot.pipeline.permits.fetch_sd_permits", new=AsyncMock(return_value=permits)
        ):
            sig = await fetch_development_signals("4364230200", "San Diego")
        assert sig["permit_count"] == 3
        assert sig["active_permit_count"] == 2  # Issued + Inspection Followup
        assert sig["unique_permit_holders"] == ["Belmont West", "HCI Systems"]
        assert "San Diego" in sig["data_source"]

    async def test_unsupported_county_returns_empty_gracefully(self):
        sig = await fetch_development_signals("123", "Broward")
        assert sig["permit_count"] == 0
        assert sig["data_source"] == "not available"


class TestChatSurfacing:
    def test_development_activity_in_grounded_payload(self):
        from plotlot.api.chat import _format_grounded_analysis

        report = MagicMock()
        report.formatted_address = "1233 Hueneme St"
        report.address = "1233 Hueneme St"
        report.municipality = "San Diego"
        report.county = "San Diego"
        report.state = "CA"
        report.zoning_district = "RM-3-7"
        report.zoning_description = ""
        report.property_record = None
        report.density_analysis = None
        report.comp_analysis = None
        report.pro_forma = None
        report.sensitivity = None
        report.entitlement = None
        report.site_risk = None
        report.coastal_overlay = None
        report.density_uplift = None
        report.extraction_verification = None
        report.warnings = []
        report.development_signals = {
            "permit_count": 20,
            "active_permit_count": 20,
            "unique_permit_holders": ["Belmont West Construction", "HCI Systems"],
            "data_source": "City of San Diego DSDPermits (Accela)",
        }

        out = _format_grounded_analysis(report)
        assert "development_activity" in out
        assert out["development_activity"]["active_permit_count"] == 20
        assert "Belmont West Construction" in out["development_activity"]["permit_holders"]

    def test_no_development_section_when_no_permits(self):
        from plotlot.api.chat import _format_grounded_analysis

        report = MagicMock()
        for attr in (
            "property_record",
            "density_analysis",
            "comp_analysis",
            "pro_forma",
            "sensitivity",
            "entitlement",
            "site_risk",
            "coastal_overlay",
            "density_uplift",
            "extraction_verification",
        ):
            setattr(report, attr, None)
        report.formatted_address = "x"
        report.address = "x"
        report.municipality = ""
        report.county = ""
        report.state = ""
        report.zoning_district = ""
        report.zoning_description = ""
        report.warnings = []
        report.development_signals = {"permit_count": 0, "active_permit_count": 0}

        out = _format_grounded_analysis(report)
        assert "development_activity" not in out
