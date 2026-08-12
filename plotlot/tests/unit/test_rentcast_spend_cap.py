"""The RentCast monthly cap is a billing guard, not a nicety.

The free Developer plan does NOT hard-stop at its 50-request quota — RentCast
bills $0.20 for every request beyond it. So an accidental retry loop is a real
invoice. These tests pin the property that matters: past the cap, no HTTP request
leaves the process.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.core.types import PropertyRecord
from plotlot.pipeline import comps_rentcast

_SUBJECT = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)


@pytest.fixture
def usage_file(tmp_path, monkeypatch):
    path = tmp_path / "usage.json"
    monkeypatch.setattr(comps_rentcast.settings, "rentcast_usage_file", str(path))
    monkeypatch.setattr(comps_rentcast.settings, "rentcast_api_key", "k")
    monkeypatch.setattr(comps_rentcast.settings, "rentcast_monthly_cap", 3)
    return path


def _ok_client(payload):
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    c.get = AsyncMock(return_value=resp)
    return c


_PAYLOAD = {"comparables": [{"formattedAddress": "1 A St", "price": 800000, "distance": 0.2}]}


class TestCap:
    @pytest.mark.asyncio
    async def test_requests_stop_dead_once_the_cap_is_reached(self, usage_file):
        client = _ok_client(_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=client):
            for i in range(3):
                out = await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
                assert out.ok, f"call {i + 1} should be inside the cap"
            assert client.get.await_count == 3

            blocked = await comps_rentcast.fetch_rentcast_comps(_SUBJECT)

        assert blocked.analysis is None
        assert "cap reached" in blocked.reason
        assert "no overage was billed" in blocked.reason
        # The decisive assertion: no fourth HTTP request was made.
        assert client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_a_failed_request_still_counts(self, usage_file):
        """RentCast meters requests, not successes. Counting only successes is what
        would let a failing retry loop bill us without ever tripping the cap."""
        c = MagicMock()
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=False)
        c.get = AsyncMock(side_effect=Exception("boom"))
        with patch("httpx.AsyncClient", return_value=c):
            for _ in range(3):
                await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
            blocked = await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
        assert "cap reached" in blocked.reason
        assert c.get.await_count == 3

    @pytest.mark.asyncio
    async def test_the_tally_survives_a_restart(self, usage_file):
        """In-memory counting would reset on every deploy or worker respawn, which
        is exactly when a loop is most likely to run away."""
        client = _ok_client(_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=client):
            await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
        assert json.loads(usage_file.read_text())["count"] == 1

        # Simulate a fresh process by reading through the public accessor again.
        used, cap = comps_rentcast.rentcast_usage()
        assert (used, cap) == (1, 3)

    @pytest.mark.asyncio
    async def test_a_new_month_resets_the_tally(self, usage_file, monkeypatch):
        usage_file.write_text(json.dumps({"month": "1999-01", "count": 999}))
        used, _ = comps_rentcast.rentcast_usage()
        assert used == 0, "a stale month must not permanently block the provider"

        client = _ok_client(_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=client):
            assert (await comps_rentcast.fetch_rentcast_comps(_SUBJECT)).ok

    @pytest.mark.asyncio
    async def test_cap_of_zero_disables_the_guard(self, usage_file, monkeypatch):
        monkeypatch.setattr(comps_rentcast.settings, "rentcast_monthly_cap", 0)
        client = _ok_client(_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=client):
            for _ in range(6):
                assert (await comps_rentcast.fetch_rentcast_comps(_SUBJECT)).ok
        assert client.get.await_count == 6

    @pytest.mark.asyncio
    async def test_an_unwritable_tally_refuses_rather_than_spends_blind(
        self, usage_file, monkeypatch
    ):
        """If the counter can't persist, every call would read 0 and the cap would
        never engage. Fail closed."""
        monkeypatch.setattr(
            comps_rentcast.Path, "write_text", MagicMock(side_effect=OSError("read-only fs"))
        )
        client = _ok_client(_PAYLOAD)
        with patch("httpx.AsyncClient", return_value=client):
            out = await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
        assert out.analysis is None
        assert client.get.await_count == 0

    @pytest.mark.asyncio
    async def test_the_cap_does_not_burn_a_request_when_unconfigured(self, usage_file, monkeypatch):
        """No key → no request → the month's allowance must be untouched."""
        monkeypatch.setattr(comps_rentcast.settings, "rentcast_api_key", "")
        out = await comps_rentcast.fetch_rentcast_comps(_SUBJECT)
        assert "not configured" in out.reason
        assert comps_rentcast.rentcast_usage()[0] == 0
