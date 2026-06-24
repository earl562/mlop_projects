"""Tests for browser_manager CAPTCHA retry logic."""

from unittest.mock import patch, AsyncMock
import pytest
from plotlot.pipeline.skills.browser_manager import run_stealth_fetch


@pytest.mark.asyncio
async def test_retry_success_on_first_attempt() -> None:
    with patch("plotlot.pipeline.skills.browser_manager._sync_stealth_scrape") as mock_scrape:
        mock_scrape.return_value = {"data": {"comps": []}, "cookies": [], "captcha_solved": False, "title": "Test"}
        result = await run_stealth_fetch("https://example.com", lambda sb: {})
        assert mock_scrape.call_count == 1
        assert "error" not in result


@pytest.mark.asyncio
async def test_retry_on_captcha_failure() -> None:
    with patch("plotlot.pipeline.skills.browser_manager._sync_stealth_scrape") as mock_scrape, \
         patch("plotlot.pipeline.skills.browser_manager.asyncio.sleep", new_callable=AsyncMock):
        mock_scrape.side_effect = [
            {"data": {}, "cookies": [], "captcha_solved": False, "error": "CAPTCHA could not be solved"},
            {"data": {"comps": [{"address": "test"}]}, "cookies": [], "captcha_solved": True, "title": "OK"},
        ]
        result = await run_stealth_fetch("https://example.com", lambda sb: {})
        assert mock_scrape.call_count == 2
        assert "error" not in result
        assert result["captcha_solved"] is True


@pytest.mark.asyncio
async def test_retry_exhausted_both_fail() -> None:
    with patch("plotlot.pipeline.skills.browser_manager._sync_stealth_scrape") as mock_scrape, \
         patch("plotlot.pipeline.skills.browser_manager.asyncio.sleep", new_callable=AsyncMock):
        mock_scrape.return_value = {"data": {}, "cookies": [], "captcha_solved": False, "error": "CAPTCHA could not be solved"}
        result = await run_stealth_fetch("https://example.com", lambda sb: {})
        assert mock_scrape.call_count == 2
        assert "CAPTCHA" in result["error"]


@pytest.mark.asyncio
async def test_no_retry_on_non_captcha_error() -> None:
    with patch("plotlot.pipeline.skills.browser_manager._sync_stealth_scrape") as mock_scrape:
        mock_scrape.return_value = {"data": {}, "cookies": [], "captcha_solved": False, "error": "Extraction failed: timeout"}
        result = await run_stealth_fetch("https://example.com", lambda sb: {})
        assert mock_scrape.call_count == 1
        assert "Extraction failed" in result["error"]
