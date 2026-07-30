#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/browser_use_land_comps_test.py
# 3. Or make executable and run:
#      chmod +x scripts/browser_use_land_comps_test.py && ./scripts/browser_use_land_comps_test.py
# ──────────────────

from __future__ import annotations

import json
from dataclasses import dataclass
from subprocess import CompletedProcess, TimeoutExpired, run
from typing import Final


SUBJECT_ADDRESS: Final = "45 NW 209 ST, Miami Gardens, FL 33169"
RESULT_MARKER: Final = "BROWSER_USE_LAND_COMP_RESULTS="


@dataclass(frozen=True, slots=True)
class LandComp:
    evidence_id: str
    source: str
    address: str
    price: str
    size: str
    fit: str
    notes: str
    screenshot: str
    url: str


def main() -> None:
    process = _run_browser_agent()
    if process.returncode != 0:
        raise SystemExit(process.stderr.strip() or "browser-use agent failed")
    comps = _parse_comps(process.stdout)
    print(f"Subject: {SUBJECT_ADDRESS}")
    print(f"Captured land listing candidates: {len(comps)}")
    for index, comp in enumerate(comps, start=1):
        print(
            f"{index}. {comp.evidence_id} | {comp.address} | {comp.price} | "
            f"{comp.size} | {comp.fit} | {comp.source}"
        )
        print(f"   {comp.notes}")
        if comp.screenshot:
            print(f"   screenshot: {comp.screenshot}")
        print(f"   {comp.url}")


def _run_browser_agent() -> CompletedProcess[str]:
    try:
        return run(
            ["browser-use"],
            input=_browser_agent_code(),
            capture_output=True,
            check=False,
            text=True,
            timeout=75,
        )
    except FileNotFoundError as exc:
        raise SystemExit("browser-use CLI is not installed or not on PATH") from exc
    except TimeoutExpired as exc:
        raise SystemExit("browser-use land comp test timed out") from exc


def _parse_comps(stdout: str) -> list[LandComp]:
    for line in stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            raw = json.loads(line.removeprefix(RESULT_MARKER))
            if not isinstance(raw, list):
                return []
            return [_to_land_comp(candidate) for candidate in raw if isinstance(candidate, dict)]
    return []


def _to_land_comp(candidate: dict[str, str]) -> LandComp:
    return LandComp(
        evidence_id=candidate.get("evidence_id", "ev_unknown").strip() or "ev_unknown",
        source=candidate.get("source", "unknown").strip() or "unknown",
        address=candidate.get("address", "address unavailable").strip() or "address unavailable",
        price=candidate.get("price", "price unavailable").strip() or "price unavailable",
        size=candidate.get("size", "size unavailable").strip() or "size unavailable",
        fit=candidate.get("fit", "needs review").strip() or "needs review",
        notes=candidate.get("notes", "visual review not captured").strip() or "visual review not captured",
        screenshot=candidate.get("screenshot", "").strip(),
        url=candidate.get("url", "").strip(),
    )


def _browser_agent_code() -> str:
    return r"""
import json
import shutil
import re
from pathlib import Path

RESULT_MARKER = "BROWSER_USE_LAND_COMP_RESULTS="
SHOT_DIR = Path("tmp/browser_use_land_comps")
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def trulia_candidates():
    new_tab("https://www.trulia.com/for_sale/Miami_Gardens,FL/LOT%7CLAND_type/")
    wait_for_load()
    text = js("document.body && document.body.innerText ? document.body.innerText : ''")
    links = js("Array.from(document.querySelectorAll('a[href*=\"/home/\"]')).map(a => ({text: a.innerText, href: a.href}))")
    lines = [clean_text(line) for line in text.splitlines()]
    out = []
    for item in links:
        address = clean_text(item.get("text"))
        if not address or "Miami Gardens" not in address:
            continue
        idx = next((i for i, line in enumerate(lines) if line == address), -1)
        nearby = lines[max(0, idx - 5):idx] if idx >= 0 else []
        price = next((line for line in reversed(nearby) if line.startswith("$")), "")
        size = next((line for line in reversed(nearby) if "ACRE" in line.upper()), "")
        out.append({
            "source": "Trulia",
            "address": address.replace(", ", ", "),
            "price": price,
            "size": size,
            "url": item.get("href", ""),
        })
    return out


def landsearch_candidates():
    new_tab("https://www.landsearch.com/properties/miami-gardens-fl")
    wait_for_load()
    links = js("Array.from(document.querySelectorAll('a[href*=\"/properties/\"]')).map(a => ({text: a.innerText, href: a.href}))")
    out = []
    by_href = {}
    for item in links:
        href = item.get("href", "")
        text = clean_text(item.get("text"))
        if "miami-gardens-fl" not in href:
            continue
        if not text and href in by_href:
            continue
        slug = href.split("/properties/", 1)[-1].split("/", 1)[0]
        parts = slug.rsplit("-", 2)
        address = parts[0].replace("-", " ").title() if parts else "Miami Gardens land listing"
        size_match = re.search(r"\d+(?:\.\d+)?\s*acres?", text)
        by_href[href] = {
            "source": "LandSearch",
            "address": address,
            "price": "",
            "size": size_match.group(0) if size_match else "",
            "url": href,
        }
    return list(by_href.values())


def acres_value(size):
    match = re.search(r"\d+(?:\.\d+)?", clean_text(size))
    return float(match.group(0)) if match else 0.0


def fit_for(candidate):
    acres = acres_value(candidate.get("size", ""))
    text = clean_text(" ".join([candidate.get("address", ""), candidate.get("price", ""), candidate.get("size", "")]))
    if "lease" in text.lower():
        return "reject"
    if 0.16 <= acres <= 0.30:
        return "strong"
    if 0.08 <= acres < 0.16 or 0.30 < acres <= 0.45:
        return "usable"
    return "weak"


def inspect_candidate(candidate, index):
    target = SHOT_DIR / f"comp_{index:02d}_{candidate['source'].lower()}.png"
    try:
        goto_url(candidate["url"])
        wait_for_load()
        body = js("document.body && document.body.innerText ? document.body.innerText : ''")
        shot = capture_screenshot()
        shutil.copyfile(shot, target)
        image_count = js("document.querySelectorAll('img').length")
    except RuntimeError as exc:
        return {
            **candidate,
            "evidence_id": f"ev_browser_comp_{index:02d}",
            "fit": fit_for(candidate),
            "notes": f"Detail inspection failed: {exc}",
            "screenshot": "",
        }
    price_match = re.search(r"priced at (\$[\d,]+)", body)
    if not price_match:
        price_match = re.search(r"\$[\d,]+", body)
    size_match = re.search(r"Lot size\s+([^\n]+)", body)
    if not size_match:
        size_match = re.search(r"This ([\d.]+-acre property)", body)
    price = price_match.group(1) if price_match and price_match.lastindex else (
        price_match.group(0) if price_match else candidate.get("price", "")
    )
    size = size_match.group(1) if size_match else candidate.get("size", "")
    candidate = {**candidate, "price": price, "size": size}
    description = clean_text(body[:900])
    notes = f"Detail page opened; image elements {image_count}; {description[:220]}"
    return {
        **candidate,
        "evidence_id": f"ev_browser_comp_{index:02d}",
        "fit": fit_for(candidate),
        "notes": notes,
        "screenshot": str(target.resolve()),
    }


candidates = []
for candidate in trulia_candidates() + landsearch_candidates():
    if candidate.get("url", "").endswith("/p2"):
        continue
    key = (candidate.get("address", "").casefold(), candidate.get("price", ""))
    if key not in {(item.get("address", "").casefold(), item.get("price", "")) for item in candidates}:
        candidates.append(candidate)

inspected = [inspect_candidate(candidate, index) for index, candidate in enumerate(candidates[:6], start=1)]
print(RESULT_MARKER + json.dumps(inspected, separators=(",", ":")))
"""


if __name__ == "__main__":
    main()
