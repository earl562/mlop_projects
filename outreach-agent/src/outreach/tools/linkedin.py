from __future__ import annotations

"""
LinkedIn automation via Playwright.
Note: LinkedIn's ToS prohibits automated messaging. This module uses browser
automation to replicate manual actions. Use responsibly — warm up slowly
(5-10 messages/day max) to minimize ban risk.
"""

import asyncio
import structlog

logger = structlog.get_logger(__name__)


async def send_connection_request(profile_url: str, note: str) -> dict:
    """
    Send a LinkedIn connection request with a note (max 200 chars).
    Requires Playwright and a logged-in LinkedIn browser session.
    Set LINKEDIN_COOKIES_PATH in env to a saved Playwright storage state.
    """
    if len(note) > 200:
        raise ValueError(f"LinkedIn connection note exceeds 200 chars: {len(note)}")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "playwright_not_installed — run: uv add playwright && playwright install chromium"}

    import os
    cookies_path = os.environ.get("LINKEDIN_COOKIES_PATH", "linkedin_session.json")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context_kwargs: dict = {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        import pathlib
        if pathlib.Path(cookies_path).exists():
            context_kwargs["storage_state"] = cookies_path

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            # Click "Connect" button
            connect_btn = page.get_by_role("button", name="Connect")
            if not await connect_btn.is_visible():
                await browser.close()
                return {"error": "connect_button_not_found", "status": "failed"}

            await connect_btn.click()
            await asyncio.sleep(1)

            # Click "Add a note"
            add_note_btn = page.get_by_role("button", name="Add a note")
            if await add_note_btn.is_visible():
                await add_note_btn.click()
                await asyncio.sleep(0.5)
                note_textarea = page.get_by_label("Add a note")
                await note_textarea.fill(note)
                await asyncio.sleep(0.5)

            # Send
            send_btn = page.get_by_role("button", name="Send")
            await send_btn.click()
            await asyncio.sleep(2)

            logger.info("linkedin_connection_sent", profile_url=profile_url)
            await context.storage_state(path=cookies_path)
            await browser.close()
            return {"status": "sent", "profile_url": profile_url}

        except Exception as exc:
            logger.error("linkedin_error", profile_url=profile_url, error=str(exc))
            await browser.close()
            return {"error": str(exc), "status": "failed"}


async def send_message(profile_url: str, message: str) -> dict:
    """
    Send a LinkedIn message to an existing connection.
    Requires an active session (already connected).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "playwright_not_installed"}

    import os, pathlib
    cookies_path = os.environ.get("LINKEDIN_COOKIES_PATH", "linkedin_session.json")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context_kwargs: dict = {}
        if pathlib.Path(cookies_path).exists():
            context_kwargs["storage_state"] = cookies_path

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            msg_btn = page.get_by_role("button", name="Message")
            if not await msg_btn.is_visible():
                await browser.close()
                return {"error": "message_button_not_visible — may not be a connection", "status": "failed"}

            await msg_btn.click()
            await asyncio.sleep(1)
            msg_box = page.get_by_role("textbox", name="Write a message…")
            await msg_box.fill(message)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

            logger.info("linkedin_message_sent", profile_url=profile_url)
            await context.storage_state(path=cookies_path)
            await browser.close()
            return {"status": "sent", "profile_url": profile_url}

        except Exception as exc:
            logger.error("linkedin_message_error", profile_url=profile_url, error=str(exc))
            await browser.close()
            return {"error": str(exc), "status": "failed"}


async def save_linkedin_session(email: str, password: str, output_path: str = "linkedin_session.json") -> dict:
    """
    Log in to LinkedIn interactively and save the browser session state.
    Run once manually: `outreach linkedin-auth`.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"error": "playwright_not_installed"}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # visible for manual 2FA if needed
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.linkedin.com/login")
        await page.fill("#username", email)
        await page.fill("#password", password)
        await page.click('button[type="submit"]')

        # Wait for manual 2FA / CAPTCHA if prompted
        print("[outreach] Complete any 2FA in the browser window, then press Enter here...")
        input()

        await context.storage_state(path=output_path)
        await browser.close()
        print(f"[outreach] LinkedIn session saved to {output_path}")
        return {"status": "saved", "path": output_path}
