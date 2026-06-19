---
name: playwright-comps
description: Playwright browser agent for scraping Zillow sold and rental comparable listings via __NEXT_DATA__ extraction. Free alternative to HasData for neighborhood comp discovery.
trust_tier: T2
verification_gate: G3
---

# Playwright Comps Skill

## When to Use

When the pipeline needs comparable sales or rental data for a property address and the HasData API is unavailable, rate-limited, or the user wants a no-cost alternative. This skill scrapes Zillow's server-side rendered search results page by extracting the `__NEXT_DATA__` JSON payload embedded in the HTML, then parses the structured listing data without touching the DOM.

## Architecture

```
Playwright Browser (stealth)
    → page.goto(search_url)
    → Extract window.__NEXT_DATA__ from <script id="__NEXT_DATA__">
    → Parse JSON → Pull listing arrays by category
    → Normalize into CompRecord dataclass
    → Return to pipeline
```

## Search URL Construction

Zillow search URLs follow a predictable pattern. Build the URL from address components:

```
https://www.zillow.com/{city-state-slug}/sold/
https://www.zillow.com/{city-state-slug}/rentals/
```

For address-specific searches, use the search endpoint:

```
https://www.zillow.com/homes/{address-slug}_rb/
```

### URL Slug Format

| Component | Pattern | Example |
|-----------|---------|---------|
| City slug | Lowercase, spaces → hyphens | `miami-gardens-fl` |
| State | Two-letter abbreviation appended to city | `miami-gardens-fl` |
| Address slug | Normalized address, spaces → hyphens | `123-main-st-miami-gardens-fl-33169` |
| Listing type | `/sold/`, `/rentals/`, or omit for for-sale | `/sold/` |

### Query Parameters

Append filtering parameters to narrow results:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `searchQueryState` | URL-encoded JSON | Advanced filters (price, beds, baths, home type) |
| `days` | Number | Sold listings: lookback window (30, 90, 365) |
| `mp` | Number | Rentals: max price filter |

## Extraction Method

### Step 1: Navigate

```python
from playwright.async_api import async_playwright

async def scrape_zillow_listings(address: str, listing_type: str = "sold"):
    slug = normalize_address_to_slug(address)
    url = f"https://www.zillow.com/homes/{slug}_rb/{listing_type}/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
```

### Step 2: Extract __NEXT_DATA__

Zillow is a Next.js application. The server renders a serialized JSON blob in a `<script>` tag with `id="__NEXT_DATA__"`. This blob contains all listing data pre-hydrated on the page.

```python
        next_data = await page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el) return null;
                return JSON.parse(el.textContent);
            }
        """)

        await browser.close()

        if not next_data:
            raise ZillowScrapeError("__NEXT_DATA__ not found on page")
```

### Step 3: Parse Listing Arrays

The `__NEXT_DATA__` JSON structure nests listing data under the Redux-style store. The relevant paths differ by listing type:

**Sold listings** live under `cat2.searchResults.listResults`:

```python
def extract_sold_listings(next_data: dict) -> list[dict]:
    try:
        results = next_data["props"]["pageProps"]["searchPageState"]["cat2"]["searchResults"]["listResults"]
        return results
    except (KeyError, TypeError):
        return []
```

**Rental listings** live under `cat1.searchResults.listResults`:

```python
def extract_rental_listings(next_data: dict) -> list[dict]:
    try:
        results = next_data["props"]["pageProps"]["searchPageState"]["cat1"]["searchResults"]["listResults"]
        return results
    except (KeyError, TypeError):
        return []
```

**For-sale listings** live under `cat1.searchResults.listResults` on non-sold, non-rental pages.

### Step 4: Normalize to CompRecord

Each listing object from Zillow carries these fields. Map them to the pipeline's `CompRecord`:

| Zillow Field | CompRecord Field | Notes |
|-------------|-----------------|-------|
| `zpid` | `source_id` | Zillow Property ID, stable key |
| `address` | `address` | Full street address string |
| `price` | `price` | Sold price or rental price |
| `hdpData.homeInfo.bedrooms` | `bedrooms` | Bedroom count |
| `hdpData.homeInfo.bathrooms` | `bathrooms` | Bathroom count (float) |
| `hdpData.homeInfo.livingArea` | `sqft` | Living area in square feet |
| `hdpData.homeInfo.lotAreaValue` | `lot_sqft` | Lot size in square feet |
| `hdpData.homeInfo.yearBuilt` | `year_built` | Construction year |
| `hdpData.homeInfo.homeType` | `property_type` | `SINGLE_FAMILY`, `CONDO`, `TOWNHOUSE`, etc. |
| `variableData.sold_date` | `sold_date` | Only present in sold listings |
| `latLong.latitude` | `latitude` | Geocoordinate |
| `latLong.longitude` | `longitude` | Geocoordinate |
| `detailUrl` | `source_url` | Full Zillow detail page URL |

```python
from plotlot.core.types import CompRecord

def normalize_zillow_listing(raw: dict, comp_type: str = "sold") -> CompRecord:
    hdp = raw.get("hdpData", {}).get("homeInfo", {})
    lat_long = raw.get("latLong", {})

    return CompRecord(
        source="zillow",
        source_id=str(raw.get("zpid", "")),
        address=raw.get("address", ""),
        price=raw.get("price", 0),
        comp_type=comp_type,
        bedrooms=hdp.get("bedrooms"),
        bathrooms=hdp.get("bathrooms"),
        sqft=hdp.get("livingArea"),
        lot_sqft=hdp.get("lotAreaValue"),
        year_built=hdp.get("yearBuilt"),
        property_type=hdp.get("homeType"),
        sold_date=raw.get("variableData", {}).get("sold_date"),
        latitude=lat_long.get("latitude"),
        longitude=lat_long.get("longitude"),
        source_url=raw.get("detailUrl", ""),
    )
```

## Full Extraction Function

```python
import asyncio
import json
from typing import Literal

from playwright.async_api import async_playwright
from plotlot.core.types import CompRecord

ListingType = Literal["sold", "rental", "for_sale"]

async def fetch_zillow_comps(
    address: str,
    listing_type: ListingType = "sold",
    max_results: int = 25,
) -> list[CompRecord]:
    """Scrape Zillow for comparable listings using __NEXT_DATA__ extraction.

    Args:
        address: Full property address (e.g., "123 Main St, Miami, FL 33169")
        listing_type: "sold", "rental", or "for_sale"
        max_results: Maximum number of listings to return

    Returns:
        List of CompRecord dataclass instances
    """
    slug = normalize_address_to_slug(address)
    url = f"https://www.zillow.com/homes/{slug}_rb/{listing_type}/" if listing_type != "for_sale" \
          else f"https://www.zillow.com/homes/{slug}_rb/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            next_data = await page.evaluate("""
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    if (!el) return null;
                    return JSON.parse(el.textContent);
                }
            """)

            if not next_data:
                return []

            cat_key = "cat2" if listing_type == "sold" else "cat1"
            search_state = next_data["props"]["pageProps"]["searchPageState"]
            raw_listings = (
                search_state
                .get(cat_key, {})
                .get("searchResults", {})
                .get("listResults", [])
            )

            comps = [
                normalize_zillow_listing(raw, listing_type)
                for raw in raw_listings[:max_results]
            ]

            return comps

        except Exception as e:
            raise ZillowScrapeError(f"Zillow scrape failed: {e}") from e

        finally:
            await browser.close()
```

## Anti-Detection Notes

Zillow actively blocks automated scraping. Without countermeasures, requests will be served CAPTCHA pages or empty responses. The following mitigations are required for production use:

### Required

| Technique | Why |
|-----------|-----|
| **Real browser fingerprinting** | Playwright with Chromium passes basic checks. Headless detection scripts look for `navigator.webdriver`, missing plugins, and WebGL variances. |
| **Realistic User-Agent** | Match a current Chrome or Firefox release on a common OS. Rotate across sessions. |
| **Viewport + language headers** | Set `Accept-Language` to `en-US` and viewport to a common desktop resolution. Avoid default headless viewport (800x600). |
| **Session management** | Reuse browser contexts across requests within a session. New context per session, not per request. |

### Recommended

| Technique | Why |
|-----------|-----|
| **Residential proxies** | Zillow rate-limits and geofences by IP. Datacenter IPs (AWS, GCP, DigitalOcean) are flagged aggressively. Rotate through residential proxy pools (Bright Data, Oxylabs, IPRoyal). |
| **playwright-stealth** | Apply the `playwright-stealth` patch to suppress automation fingerprints: `navigator.webdriver`, `chrome.runtime`, permissions API, and plugin enumeration. |
| **Delay between requests** | Add randomized 3-8 second delays between page loads. Do not fire requests faster than human browsing cadence. |
| **Cache `__NEXT_DATA__`** | The JSON blob changes infrequently. Cache successful extractions by `zpid` for 24 hours to reduce repeat requests. |

### Installation

```bash
uv add playwright playwright-stealth
playwright install chromium
```

### Stealth Setup

```python
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def create_stealth_page():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    page = await context.new_page()
    await stealth_async(page)
    return playwright, browser, context, page
```

## __NEXT_DATA__ Structure Reference

The full JSON payload follows Next.js conventions. The listing-adjacent structure:

```
props.pageProps.searchPageState
├── cat1                          # Primary category (for-sale, rentals)
│   └── searchResults
│       ├── listResults[]         # Array of listing objects
│       ├── totalResultCount      # Total matching listings
│       └── pagination
│           ├── currentPage
│           └── totalPages
├── cat2                          # Secondary category (sold listings)
│   └── searchResults
│       ├── listResults[]         # Array of sold listing objects
│       ├── totalResultCount
│       └── pagination
├── mapResults[]                  # Map view results (less detail)
└── regionResults[]               # Regional aggregate data
```

Field mappings may shift between Zillow deployments. If extraction returns empty or malformed data, inspect the live `__NEXT_DATA__` blob by visiting the target URL and running `JSON.parse(document.getElementById('__NEXT_DATA__').textContent)` in the browser console. Diff against the expected paths above.

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| `__NEXT_DATA__` not found | CAPTCHA page served instead of search results | Rotate IP, add delay, check proxy health |
| `searchPageState` missing | Zillow restructured the payload | Inspect live blob, update extraction paths |
| `cat1`/`cat2` missing | Page type mismatch (e.g., `/sold/` on a rental-only region) | Fall back to the other category key |
| `listResults` empty | No listings match the search criteria | Return empty list, widen search radius in next attempt |
| Timeout | Slow proxy or Zillow anti-bot delay page | Increase timeout to 60s, use `domcontentloaded` instead of `networkidle` |

## CLI Integration

Register this skill in the chat agent's tool manifest so the LLM can invoke it during `c=comps` pipeline steps:

```python
# In plotlot.api.chat.tools
{
    "name": "scrape_zillow_comps",
    "description": "Scrape Zillow sold/rental comparable listings for a property address using Playwright browser automation.",
    "parameters": {
        "address": "Full property address string",
        "listing_type": "'sold', 'rental', or 'for_sale'",
        "max_results": "Maximum listings to return (default 25)",
    },
}
```

## Limitations

- **Single page only.** Zillow paginates at ~40 listings per page. Multi-page scraping requires clicking "Next" and introduces additional detection risk. The current implementation captures page 1 only.
- **US only.** Zillow operates in the United States. Canadian listings use a different domain and payload structure.
- **No historical depth.** The `__NEXT_DATA__` blob contains only the listings rendered on the current page. Older sold records require filtered search with `days` parameter.
- **Rate limit risk.** Zillow's anti-bot defenses evolve. What works today may require updated fingerprinting tomorrow. Budget for periodic maintenance.
- **Free tier proxies.** Residential proxy pools start around $5-10/month for hobby-tier usage. At scale, factor proxy costs into the comparison against HasData API pricing.

## Comparison: Playwright vs. HasData API

| Dimension | Playwright (this skill) | HasData API |
|-----------|------------------------|-------------|
| Cost | Proxy costs only (~$10/mo hobby) | Pay-per-request or monthly subscription |
| Freshness | Live data from Zillow | API cache may lag 1-24 hours |
| Rate limits | Self-imposed via delays | API-enforced tier limits |
| Maintenance | Anti-detection requires updates | API provider handles scraping |
| Coverage | US Zillow only | Multi-source (Zillow, Realtor.com, Redfin) |
| Determinism | __NEXT_DATA__ paths may shift | Stable API contract |
| Legal risk | Scraping Zillow (TOS gray area) | Licensed data access |

Use this skill as a fallback when HasData is unavailable or for development and testing where cost savings outweigh maintenance burden.
