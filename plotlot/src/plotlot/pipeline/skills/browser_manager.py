"""SeleniumBase UC+CDP stealth browser manager.

Provides a synchronous stealth browsing context using SeleniumBase's
``SB(uc=True) + activate_cdp_mode()`` pattern — the recommended approach
from the "Undetectable Automation 5th Edition" video for bypassing
PerimeterX, Cloudflare, and DataDome bot detection.

Key stealth layers (per the video):
1. **UC Mode** — modified chromedriver that disconnects/reconnects at
   strategic times to avoid WebDriver detection.
2. **CDP Mode** — Chrome DevTools Protocol commands (input.dispatchMouseEvent
   etc.) that mimic hardware events; websites can't distinguish from real
   user input (isTrusted=true).
3. **PyAutoGUI** — for PerimeterX "press and hold" CAPTCHAs, uses real
   mouse via ``gui_click_and_hold("#px-captcha", duration)``.
4. **Unbranded Chromium** — optionally use Chromium instead of Google Chrome
   (stealthier on some sites per the video's Reddit demo).
5. **Ad blocking** — reduces network traffic fingerprint.

The async pipeline calls ``run_stealth_fetch()`` which executes the sync
SB() session in a thread executor, returning extracted page content.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SeleniumBase import (optional)
# ---------------------------------------------------------------------------

try:
    from seleniumbase import SB  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    SB = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ExtractFn = Callable[[Any], dict[str, Any]]
"""Sync function that receives the SB instance and returns extracted data."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PerimeterX "press and hold" CAPTCHA selector.
_PX_CAPTCHA_SELECTOR = "#px-captcha"

# Hold durations for press-and-hold (seconds). Per the video's Walmart demo.
_PX_HOLD_PRIMARY = 7.2
_PX_HOLD_RETRY = 4.2

# Sleep after CAPTCHA solve attempts (seconds).
_POST_CAPTCHA_SLEEP = 4.2
_POST_RETRY_SLEEP = 3.2

# Delay after page navigation for JS rendering (seconds).
_POST_NAV_DELAY = 3.0


# ---------------------------------------------------------------------------
# CAPTCHA detection & solving
# ---------------------------------------------------------------------------


def _is_captcha_page(sb: Any) -> bool:
    """Detect PerimeterX / bot-detection block pages."""
    try:
        title = sb.get_title()
        if "denied" in title.lower():
            return True
    except Exception:
        pass
    try:
        return sb.is_element_visible(_PX_CAPTCHA_SELECTOR)
    except Exception:
        return False


def _solve_perimeterx_captcha(sb: Any) -> bool:
    """Solve PerimeterX "press and hold" CAPTCHA via gui_click_and_hold.

    Uses PyAutoGUI under the hood to simulate a real mouse press-and-hold
    on the px-captcha element. Returns True if CAPTCHA is gone after attempts.
    """
    if not sb.is_element_visible(_PX_CAPTCHA_SELECTOR):
        return True

    logger.info("PerimeterX CAPTCHA detected — gui_click_and_hold %.1fs", _PX_HOLD_PRIMARY)
    try:
        sb.cdp.gui_click_and_hold(_PX_CAPTCHA_SELECTOR, _PX_HOLD_PRIMARY)
    except Exception as exc:
        logger.warning("gui_click_and_hold failed: %s — trying solve_captcha", exc)
        try:
            sb.solve_captcha()
        except Exception:
            pass

    sb.sleep(_POST_CAPTCHA_SLEEP)

    if sb.is_element_visible(_PX_CAPTCHA_SELECTOR):
        logger.info("CAPTCHA persists — retrying with %.1fs hold", _PX_HOLD_RETRY)
        try:
            sb.cdp.gui_click_and_hold(_PX_CAPTCHA_SELECTOR, _PX_HOLD_RETRY)
        except Exception:
            pass
        sb.sleep(_POST_RETRY_SLEEP)

    return not sb.is_element_visible(_PX_CAPTCHA_SELECTOR)


# ---------------------------------------------------------------------------
# Core sync scrape function (runs in thread executor)
# ---------------------------------------------------------------------------


def _sync_stealth_scrape(
    url: str,
    extract_fn: ExtractFn,
    *,
    use_chromium: bool = True,
    headless: bool = False,
    ad_block: bool = True,
    locale: str = "en",
    cookies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a stealth scrape using SB(uc=True) + activate_cdp_mode().

    This function is SYNCHRONOUS — call via ``asyncio.to_thread()`` from
    async code.

    Args:
        url: URL to navigate to.
        extract_fn: Sync function(sb) -> dict that extracts data from the page.
        use_chromium: Use unbranded Chromium (stealthier per the video).
        headless: Run headless. Defaults False — headed is stealthier, and
            PyAutoGUI (for CAPTCHAs) requires a headed browser.
        ad_block: Block ads to reduce network fingerprint.
        locale: Browser locale.
        cookies: Cookies from a previous session to reuse (CAPTCHA bypass).

    Returns:
        Dict with keys: ``data`` (extract_fn result), ``cookies`` (session
        cookies for reuse), ``captcha_solved`` (bool), ``title`` (page title).
        On failure, includes ``error`` key.
    """
    if SB is None:
        return {"error": "seleniumbase not installed", "data": {}, "cookies": []}

    result: dict[str, Any] = {"data": {}, "cookies": [], "captcha_solved": False, "title": ""}

    try:
        sb_kwargs: dict[str, Any] = {
            "uc": True,
            "test": True,
            "ad_block": ad_block,
            "locale": locale,
        }
        if use_chromium:
            sb_kwargs["use_chromium"] = True
        if headless:
            sb_kwargs["headless"] = True

        with SB(**sb_kwargs) as sb:
            # Activate CDP mode for maximum stealth
            sb.activate_cdp_mode(url)

            # Load cookies from previous session if provided
            if cookies:
                for cookie in cookies:
                    try:
                        sb.add_cookie(cookie)
                    except Exception:
                        pass
                sb.reload()
                sb.sleep(_POST_NAV_DELAY)

            # Random sleep to mimic human behavior (per video recommendation)
            sb.sleep(random.uniform(1.0, 2.5))

            # Check for CAPTCHA and solve if needed
            captcha_was_solved = False
            if _is_captcha_page(sb):
                captcha_was_solved = _solve_perimeterx_captcha(sb)
                if captcha_was_solved:
                    sb.reload()
                    sb.sleep(_POST_NAV_DELAY)
                else:
                    logger.error("CAPTCHA could not be solved for %s", url)
                    result["error"] = "CAPTCHA could not be solved"
                    result["title"] = sb.get_title()
                    try:
                        result["cookies"] = sb.get_all_cookies()
                    except Exception:
                        pass
                    return result
            else:
                sb.sleep(_POST_NAV_DELAY)

            result["title"] = sb.get_title()
            result["captcha_solved"] = captcha_was_solved

            # Run extraction
            try:
                result["data"] = extract_fn(sb)
            except Exception as exc:
                logger.exception("Extraction function failed: %s", exc)
                result["error"] = f"Extraction failed: {exc}"

            # Save cookies for reuse in subsequent requests
            try:
                result["cookies"] = sb.get_all_cookies()
            except Exception:
                pass

    except Exception as exc:
        logger.exception("Stealth scrape failed for %s: %s", url, exc)
        result["error"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------


_CAPTCHA_RETRY_DELAY = 30
_CAPTCHA_ERROR_MARKER = "CAPTCHA could not be solved"


async def run_stealth_fetch(
    url: str,
    extract_fn: ExtractFn,
    *,
    use_chromium: bool = True,
    headless: bool = False,
    ad_block: bool = True,
    locale: str = "en",
    cookies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Async wrapper that runs the sync SB() scrape in a thread executor.

    If the first attempt fails with a CAPTCHA error, waits 30s and retries
    once. Non-CAPTCHA errors are returned immediately without retry.

    Args:
        url: URL to navigate to.
        extract_fn: Sync function(sb) -> dict that extracts page data.
        use_chromium: Use unbranded Chromium (stealthier).
        headless: Run headless. Defaults False (PyAutoGUI needs headed).
        ad_block: Block ads.
        locale: Browser locale.
        cookies: Reusable session cookies from a previous scrape.

    Returns:
        Dict with ``data``, ``cookies``, ``captcha_solved``, ``title``,
        and optionally ``error``.
    """
    scrape_kwargs = {
        "use_chromium": use_chromium,
        "headless": headless,
        "ad_block": ad_block,
        "locale": locale,
        "cookies": cookies,
    }

    result = await asyncio.to_thread(_sync_stealth_scrape, url, extract_fn, **scrape_kwargs)

    if _CAPTCHA_ERROR_MARKER in result.get("error", ""):
        logger.warning("CAPTCHA failed for %s — retrying after %ds", url, _CAPTCHA_RETRY_DELAY)
        await asyncio.sleep(_CAPTCHA_RETRY_DELAY)
        if result.get("cookies"):
            scrape_kwargs["cookies"] = result["cookies"]
        result = await asyncio.to_thread(_sync_stealth_scrape, url, extract_fn, **scrape_kwargs)

    return result
