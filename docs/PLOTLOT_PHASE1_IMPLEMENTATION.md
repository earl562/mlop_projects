# PlotLot v2 — Phase 1: Building the Data Foundation

## What I Built and Why

PlotLot is an AI-powered zoning analysis platform for South Florida real estate. Before I could build any agents, fine-tune any models, or stand up any inference infrastructure, I needed to solve a fundamental problem: **where does the data come from?**

South Florida has 107 separate zoning jurisdictions across three counties. Each county runs its own GIS infrastructure with different APIs, different coordinate systems, different field names, and different data formats. There is no unified API. No one has stitched this together before.

Phase 1 is the data acquisition pipeline — the piece that takes a raw street address and returns structured property intelligence: which municipality it's in, what the zoning district is, and the parcel details (lot size, owner, assessed value, year built). This is the foundation that every downstream component depends on — the RAG pipeline needs to know which municipality's ordinance to retrieve, the agent needs to know the zoning code to look up setbacks, and the constraint calculator needs the lot dimensions to compute max allowable units.

I built this to run at **$0/month** using only free public APIs. No paid geocoders, no licensed parcel databases, no third-party GIS subscriptions. The entire pipeline runs against publicly available ArcGIS REST endpoints that the counties themselves maintain.

**The result:** 30 addresses tested across all three counties, 28/30 successfully resolved with municipality, zoning, and parcel data. 100% coverage of all 104 incorporated municipalities and 3 unincorporated areas.

---

## The Pipeline

```
"100 NE 1st Ave, Miami, FL 33132"
        │
        ▼
   ┌─────────────┐
   │  Geocode     │   Geocodio (2,500 free/day) → Census Bureau (unlimited)
   │  → lat/lng   │
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │  County      │   Bounding-box lookup — no API call, instant
   │  Detection   │
   └──────┬──────┘
          │
    ┌─────┴─────────────────────┐
    │   Route by county          │
    │   (each county is different)│
    └─────┬─────────┬───────────┘
          │         │
     Miami-Dade    Broward / Palm Beach
     (special)     (generic)
          │         │
          ▼         ▼
   Combined       Separate
   zoning +       municipal boundary
   municipality   + zoning layers
   from one       + FL Statewide
   ArcGIS layer   Cadastral for parcels
          │         │
          ▼         ▼
   ┌──────────────────────┐
   │  PropertyReport       │
   │  municipality, zoning,│
   │  parcel, coordinates  │
   └──────────────────────┘
```

---

## How I Built It — Problem by Problem

### 1. Getting Coordinates from an Address

**The problem:** Everything downstream — municipality detection, zoning lookup, parcel queries — requires latitude/longitude coordinates. I needed a geocoder that was free, reliable, and accurate enough that a coordinate wouldn't land on the wrong side of a municipal boundary.

**What I did:** I built an async geocoding client with cascading fallback. Geocodio is the primary provider — it gives rooftop-level accuracy and 2,500 free lookups per day, which is more than enough for development and early users. If the Geocodio API key isn't configured or the call fails, it falls back to the US Census Bureau geocoder, which is unlimited and free but uses range interpolation (it estimates where on a block an address is, rather than pinpointing the building).

**Why this matters for ML/LLMOps:** This is the first data quality gate in the pipeline. Geocoding accuracy directly determines whether every downstream query hits the right polygon. I saw this firsthand — a Sweetwater address geocoded 50 meters off by the Census geocoder and landed in unincorporated Miami-Dade instead of the City of Sweetwater. In a production ML system, this is the kind of silent data quality issue that corrupts training data and causes model drift. You'd monitor geocoding source distribution and accuracy scores as pipeline health metrics.

---

### 2. Figuring Out Which County You're In

**The problem:** Once I have coordinates, I need to know which county they're in, because each county has completely different GIS infrastructure.

**What I did:** Simple bounding-box lookup — hardcoded lat/lng ranges for each county. No API call needed, instant response. The boxes overlap slightly at borders (Miami-Dade checks first), which is fine because the GIS layers themselves handle precise boundaries.

**Why I didn't overthink this:** A spatial query against a county boundary layer would be more precise, but it would add an API call for something that's wrong approximately never. The bounding boxes cover the populated areas of all three counties. This is a case where the simple solution is the right solution.

---

### 3. Identifying the Municipality — Where It Got Interesting

This was the hardest part of Phase 1. Each county handles municipal boundaries differently, and the initial approach failed in ways I didn't expect.

#### Miami-Dade: The Wrong Layer Problem

**The problem:** I initially used Layer 24 of Miami-Dade's `MD_LandInformation/MapServer` for municipal boundaries. When I tested with downtown Miami — an address that is unambiguously inside the City of Miami — the pipeline returned "unincorporated." That's obviously wrong.

**How I debugged it:** I queried the MapServer root endpoint (`?f=json`) to list all available layers. Layer 24 turned out to be named "Property (PaGis)" — it's a property layer, not municipal boundaries at all. The initial research had misidentified it.

**What I discovered:** While scanning the available layers, I found that the `MD_Zoning/MapServer` has a Layer 2 (Municipal Zoning) that returns **both** the municipality name (`MUNICNAME`) and the zoning code (`ZONE`) in a single query. This was better than what I was originally trying to do — instead of two separate API calls (one for municipality, one for zoning), I could get both from one call.

**The fix:** I rewrote the Miami-Dade handling into a combined method `_miami_dade_zoning_and_municipality()`. It queries Layer 2 first (covers all 34 incorporated municipalities), and falls back to Layer 1 (unincorporated zoning) if the result indicates unincorporated territory.

**A subtle bug this introduced:** Layer 2 actually covers the entire county, including unincorporated areas. For unincorporated points, it returns `MUNICNAME='UNINCORPORATED'` and `ZONE='NONE'`. The string `"NONE"` is truthy in Python, so my code initially accepted it as a valid zoning code. I had to add explicit checks to skip results where the zone is literally the string "NONE" and let it fall through to Layer 1 for the real unincorporated zoning code.

**The result:** All 34 Miami-Dade municipalities correctly identified, and I cut the API calls from 2 to 1 for incorporated areas.

#### Broward: Wrong Server, Wrong Layer

**The problem:** The initial Broward endpoint (`New_BCPA_basemap2/MapServer/390`) returned an ArcGIS 400 error. The service existed, but the layer number was wrong.

**How I found the right endpoint:** I systematically probed every ArcGIS server associated with Broward County — `gisweb-adapters.bcpa.net`, `gisweb.bcpa.net`, `gis.broward.org` (was down), and the ArcGIS Online hosted services. I found that `BCPA_EXTERNAL_JAN26/MapServer` had the data I needed: Layer 3 = "City Limits" with a `CITYNAME` field covering all 31 Broward municipalities.

**Something worth noting:** The BCPA service name includes a date — `JAN26`. The Broward County Property Appraiser rotates these services periodically. This is a production concern — if you deploy this and walk away, it will break when they rotate to `JUL26` or whenever the next update is. In a production ML platform, this is exactly the kind of external dependency that needs automated health checks and alerting.

#### Palm Beach: Coordinate System Mismatch

**The problem:** Palm Beach's GIS layers use EPSG:2881 (Florida State Plane East, measured in US feet) as their native coordinate system. When you send a WGS84 (GPS-style lat/lng) point query, the ArcGIS server has to reproject it on the fly. This reprojection introduces floating-point precision errors — enough that a point query can miss a polygon entirely, especially narrow ones near boundaries.

**How I solved it:** Instead of sending a single point, I send a small bounding box — about 100 meters on each side. This is called an "envelope query" in ArcGIS terms. The envelope is large enough to absorb the reprojection precision loss but small enough that it won't accidentally hit adjacent polygons in most cases. I made this configurable per-endpoint with a `use_envelope: True` flag so it only applies where needed.

**The result:** Palm Beach municipality, zoning, and parcel queries all work reliably. Without the envelope, they were failing silently — returning zero results with no error.

#### Name Normalization Across All Counties

**The problem:** Every county formats municipality names differently. Miami-Dade returns mixed case (`"Miami Shores"` but also `"OPA-LOCKA"`). Broward returns all caps (`"FORT LAUDERDALE"`). Palm Beach returns all caps (`"WEST PALM BEACH"`). And there are special entries like `"BMSD"` (Broward's unincorporated area), `"TRIBAL LAND"`, and `"COUNTY REGIONAL FACILITY"` that need to be handled.

**What I built:** A `municipalities.py` module with the complete reference list of all 104 municipalities and a normalization function that converts raw GIS names into consistent, canonical form. It handles title-casing with special rules (e.g., "Lauderdale-by-the-Sea" not "Lauderdale-By-The-Sea"), override mappings for known quirks, and detection of unincorporated area names.

**Why this matters:** When the agent system goes to look up zoning ordinances, it needs to match on municipality name. If Fort Lauderdale sometimes comes through as "FORT LAUDERDALE" and sometimes as "Fort Lauderdale", that's a data join failure waiting to happen. Normalization at the source prevents an entire category of downstream bugs.

---

### 4. Getting the Zoning Code

**The problem:** There's no standard for how ArcGIS layers name their zoning fields. Miami-Dade uses `ZONE`. Broward has `ZONE_NAME` (with the actual code) and `ZONING` (which contains a single space character). Palm Beach uses `FCODE` for the code and `ZONING_DESC` for the description.

**What I did:** I implemented a fallback chain that tries every known field name in priority order, with a helper function that strips whitespace before checking truthiness. This is what caught the Broward bug — their `ZONING` field contains `' '` (a single space), which Python considers truthy. Without the whitespace strip, the code would pick up that space instead of the actual zoning code in `ZONE_NAME`.

**The result:** Zoning codes extracted correctly from all three counties despite completely different schemas. Downtown Miami returns `T6-80-O` (Miami 21 form-based code), Fort Lauderdale returns `RAC-CC` (Regional Activity Center - City Center), West Palm Beach returns `QGD-10 (city)` (Quadrille Garden District).

---

### 5. Retrieving Parcel Data

This is where the county differences really diverge.

#### Miami-Dade: Address-Based Queries

**The problem:** Miami-Dade's parcel layer uses EPSG:2236 (State Plane, US feet), and unlike Palm Beach's EPSG:2881, this layer does NOT support on-the-fly reprojection from WGS84. Every spatial query returned zero features — no error, just empty results.

**How I figured this out:** I tested the spatial query directly against the endpoint, got zero results, then tested an address-based WHERE query against the same endpoint and got back complete parcel data. The layer supports attribute queries just fine — it's only the spatial/geometry queries that fail because it can't reproject.

**The fix:** For Miami-Dade only, I use address-based queries instead of spatial queries. The tricky part is address normalization — ArcGIS's `LIKE` operator requires the address to match the format in the database. I strip ordinals ("1st" → "1"), remove street suffixes ("AVE", "BLVD"), collapse whitespace, and append a wildcard. This means the pipeline needs to pass the original address string through from the geocoding step, not just coordinates.

#### Broward & Palm Beach: County Layers Were Useless

**The problem:** I discovered that Broward's BCPA parcel layer only contains the folio number — no owner name, no assessed value, no year built, nothing useful. Palm Beach was even worse — their county parcel layer turned out to be a cached tile layer with literally three fields: FID, Id, and "Cached." It's designed for rendering map tiles, not data queries.

**What I found:** The Florida Department of Revenue publishes a statewide cadastral dataset on ArcGIS Online with 100+ fields — owner, address, assessed value, year built, living area, sale prices, land use codes. It covers every parcel in the state. It's free, public, and requires no authentication.

**The implementation:** Both Broward and Palm Beach now query this statewide dataset with a county filter (`CO_NO=16` for Broward, `CO_NO=60` for Palm Beach). I discovered the correct county codes through testing — FDOR uses its own numbering system, not FIPS codes. My first attempt used `CO_NO=6` for Broward and got zero results. Removing the filter returned data with `CO_NO=16`. A small bug, but the kind of thing that's invisible until you test against real data.

**One more data type issue:** The statewide dataset returns zip codes as integers (`33401` instead of `"33401"`). Pydantic raised a validation error. I added a `@field_validator` to coerce numeric values to strings before validation.

---

### 6. Putting It All Together

The `PropertyLookup` pipeline chains everything: geocode → detect county → get municipality → get zoning → get parcel. Each step is wrapped in error handling so a failure in one doesn't prevent the others from running. The pipeline marks success as long as geocoding and county detection succeed — partial results (e.g., got municipality and zoning but no parcel) are still useful.

The one integration issue I hit was that after rewriting the GIS client to use address-based queries for Miami-Dade parcels, the pipeline was still calling `get_parcel(lat, lng, county)` without passing the address. I updated the interface to accept optional `address` and `city` parameters, and the pipeline now extracts the city from the municipality result to pass through.

---

## Coverage Verification

I verified coverage by querying each county's GIS layer for every distinct municipality name it knows about, then cross-referencing against the official list from each county's government website.

| County | Official Count | GIS Layer Count | Coverage |
|--------|---------------|-----------------|----------|
| Miami-Dade | 34 municipalities | 34 returned from Layer 2 | 100% |
| Broward | 31 municipalities | 31 + BMSD (unincorporated) + 2 special areas | 100% |
| Palm Beach | 39 municipalities | 39 returned from Layer 5 | 100% |
| **Total** | **104 municipalities + 3 unincorporated** | **107** | **100%** |

---

## What I'd Build Differently in Production

**Observability from day one.** Every external API call should emit structured telemetry — endpoint URL, response time, feature count, HTTP status, error details. In an ML platform context, this feeds into data pipeline monitoring. If the BCPA rotates their service name and our zoning queries start returning empty, we need to know within minutes, not when a user reports it.

**Endpoint health checks on startup.** Rather than discovering broken URLs through test failures, a startup probe that validates each endpoint returns the expected fields would catch configuration drift before it hits users. This is the same pattern you'd use for model serving health checks — verify the dependency graph is healthy before accepting traffic.

**Retry with backoff and circuit breakers.** County GIS servers have variable uptime. A production pipeline needs exponential backoff, jitter, and circuit breakers so a slow or failing endpoint doesn't cascade into pipeline-wide timeouts. The same patterns apply to model inference endpoints — if vLLM is slow, you don't want every request queuing up behind it.

**Geocoding accuracy monitoring.** Track the distribution of geocoding sources (Geocodio vs Census) and flag when Census fallback rates spike. Census geocoding has lower accuracy and can place coordinates in the wrong municipality near borders. This is analogous to monitoring embedding model performance — degraded quality in an upstream component silently corrupts everything downstream.

---

## What This Means for the ML Pipeline

This Phase 1 pipeline is the data ingestion layer for the entire system. Every component that comes next depends on this data being correct:

- **Training data:** When I fine-tune a model on zoning Q&A pairs, the ground truth comes from this pipeline. If the pipeline misidentifies a municipality or returns the wrong zoning code, that error propagates into the training data and the model learns the wrong answer.

- **RAG retrieval:** The agent needs to know exactly which municipality's zoning ordinance to search. Fort Lauderdale's RAC-CC district has completely different setback rules than Miami's T6-80-O. If the pipeline returns the wrong municipality, the RAG system retrieves the wrong document and the agent confidently gives the user incorrect information.

- **Agent tool reliability:** The property data agent uses this pipeline as a tool. If the tool returns inconsistent or missing data, the agent either hallucinates to fill gaps or gives the user an incomplete analysis. Reliable tools make reliable agents.

The challenges I solved here — coordinate system mismatches, schema heterogeneity across data sources, data type coercion, name normalization, silent failures that return empty results instead of errors — are the exact same challenges you face in any production ML data pipeline. The specific domain is real estate GIS, but the engineering patterns are universal.

---

## Cost

| Service | Cost |
|---------|------|
| US Census Geocoder | $0 |
| Geocodio (free tier) | $0 |
| Miami-Dade ArcGIS (public) | $0 |
| Broward BCPA ArcGIS (public) | $0 |
| Palm Beach ArcGIS (public) | $0 |
| FL Statewide Cadastral (public) | $0 |
| **Total monthly** | **$0** |

---

## File Structure

```
plotlot-v2/
├── pyproject.toml                     # Package config, 5 dependency groups
├── docker-compose.yml                 # PostgreSQL + pgvector (Phase 2)
├── scripts/init_db.sql                # DB schema (Phase 2)
├── src/plotlot/
│   ├── cli.py                         # CLI: plotlot "123 Main St, Miami FL"
│   ├── config.py                      # Pydantic Settings (.env)
│   ├── geocoding/
│   │   ├── client.py                  # Geocodio → Census fallback
│   │   └── models.py                  # GeocodingResult
│   ├── gis/
│   │   ├── client.py                  # GISClient — spatial + WHERE queries
│   │   ├── endpoints.py               # Per-county ArcGIS URL configs
│   │   ├── models.py                  # County, ParcelData, ZoningData, MunicipalityData
│   │   └── municipalities.py          # 104 municipalities + name normalization
│   └── pipeline/
│       ├── lookup.py                  # PropertyLookup orchestration
│       └── models.py                  # PropertyReport + summary()
```
