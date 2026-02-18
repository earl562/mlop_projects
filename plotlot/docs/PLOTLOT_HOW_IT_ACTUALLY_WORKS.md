# PlotLot v2 — How It Actually Works

### The real engineering: from address input to maximum allowable units.

---

## The Problem (Why This Is Hard)

A real estate investor types: **"123 NW 5th Ave, Fort Lauderdale, FL"**

To determine maximum allowable units, you need to:

1. **Geocode** the address → lat/lng
2. **Identify the parcel** → lot size, dimensions
3. **Determine the jurisdiction** → Is this in the City of Fort Lauderdale? Or unincorporated Broward County?
4. **Get the zoning district code** → e.g., "RMM-25"
5. **Find THAT municipality's zoning ordinance** → Fort Lauderdale's ULDR, not Broward County's code
6. **Extract the regulations** → setbacks, density, FAR, lot coverage, height, parking
7. **Calculate maximum units** → The MINIMUM of multiple constraints (density, FAR, buildable area, parking)

**Why nobody's built this properly:** Step 3-6 is where it breaks. South Florida has **~104 separate zoning jurisdictions** across the three counties. Each has its own zoning code, published on different platforms, in different formats.

| County | Municipalities | Unincorporated |
|--------|---------------|----------------|
| Miami-Dade | 34 | Yes |
| Broward | 31 | Yes |
| Palm Beach | 39 | Yes |
| **Total** | **104** | **separate zoning codes** |

This isn't a "query the API" problem. This is a **multi-jurisdiction data engineering + NLP** problem.

---

## The Data Sources (All Free)

Here's what we have to work with — and it costs $0.

### GIS Data (County ArcGIS REST Endpoints — FREE, No Auth Required)

All three counties run public ArcGIS servers. You can query them programmatically with zero authentication.

**Miami-Dade County:**
| Layer | Endpoint | What It Returns |
|-------|----------|----------------|
| Parcels | `gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer/26` | Folio, address, lot size, zoning code (PRIMARY_ZONE), year built, bedrooms, bathrooms, building area, land/building/total value |
| Unincorporated Zoning | `gisweb.miamidade.gov/arcgis/rest/services/LandManagement/MD_Zoning/MapServer/1` | Zoning district for unincorporated areas |
| Municipal Zoning | `gisweb.miamidade.gov/arcgis/rest/services/LandManagement/MD_Zoning/MapServer/2` | Zoning district within municipalities |
| Municipal Boundaries | Open Data Hub → Municipal Boundary dataset | Which municipality a point falls in |

**Broward County:**
| Layer | Endpoint | What It Returns |
|-------|----------|----------------|
| BMSD Zoning | `geohub-bcgis.opendata.arcgis.com` → BMSD Zoning dataset | Zoning for unincorporated areas |
| City Boundaries | BCPA MapServer Layer 390 | Which municipality a point falls in |
| Parcels | BCPA MapServer | Folio, address, lot data, zoning |

**Palm Beach County:**
| Layer | Endpoint | What It Returns |
|-------|----------|----------------|
| Parcels | `maps.co.palm-beach.fl.us/arcgis/rest/services/Parcels/Parcels/MapServer/0` | Parcel data with 100+ fields |
| Zoning | `maps.co.palm-beach.fl.us/arcgis/rest/services/OpenData/Planning_Open_Data/MapServer/9` | Zoning district |
| Municipal Boundaries | `maps.co.palm-beach.fl.us/arcgis/rest/services/OpenData/Boundaries_Open_Data/MapServer/5` | Municipality lookup |

### How to Query (Point-in-Polygon)

```python
import httpx

async def get_zoning_district(lat: float, lng: float) -> dict:
    """Query Miami-Dade ArcGIS for zoning at a coordinate."""
    url = (
        "https://gisweb.miamidade.gov/arcgis/rest/services"
        "/LandManagement/MD_Zoning/MapServer/1/query"
    )
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "json",
    }
    resp = await httpx.AsyncClient().get(url, params=params)
    data = resp.json()
    return data["features"][0]["attributes"]
```

This returns the zoning district code, zoning description, and geometry — **for free, with no API key.**

### Geocoding

| Provider | Free Tier | Why |
|----------|-----------|-----|
| **Geocodio** | 2,500/day | US-focused, no storage restrictions, commercial OK |
| **US Census Geocoder** | Unlimited | Free, batch capable (10K at once), but interpolated accuracy |
| **Google Maps** | 10,000/month | Best accuracy, but 30-day cache limit |

**Recommendation:** Geocodio for primary (free, accurate), Census as fallback (free, unlimited).

---

## The Real Challenge: Zoning Ordinances

Getting the zoning district CODE is easy (ArcGIS query returns "RMM-25"). Knowing what "RMM-25" MEANS is the hard part.

### Where Zoning Ordinances Live

Each municipality publishes its zoning code on different platforms:

| Platform | Format | Municipalities |
|----------|--------|---------------|
| **Municode** | HTML (structured) | Miami-Dade County, Coral Gables, Boca Raton, Doral, West Palm Beach, many others |
| **American Legal** | HTML | City of Hollywood |
| **eLaws** | HTML | Miami-Dade County, Fort Lauderdale |
| **Encode Plus** | HTML (interactive) | West Palm Beach |
| **Direct PDF** | PDF | Miami (Miami 21), Palm Beach County ULDC |
| **Gridics CodeHUB** | Structured/Interactive | Miami, Fort Lauderdale, Coral Gables, Hollywood (proprietary, no API) |

### What We Need to Extract From Each Ordinance

For every zoning district, we need:

| Field | Example (Miami-Dade RU-3) | Type |
|-------|--------------------------|------|
| **Front setback** | 25 ft | Number |
| **Rear setback** | 25 ft | Number |
| **Interior side setback** | 20 ft | Number |
| **Street side setback** | 25 ft | Number |
| **Max lot coverage** | 40% | Percentage |
| **Max building height** | 35 ft / 2 stories | Number |
| **Max density** | 13 units/acre | Number |
| **Min lot size per unit** | 3,350 sq ft | Number |
| **Floor Area Ratio (FAR)** | Varies by height | Number |
| **Min unit size** | Varies | Number |
| **Parking per unit** | 1.5 spaces | Number |
| **Open space** | 20% | Percentage |

### The Complication: Setbacks Aren't Simple Numbers

Setbacks vary by:
- **Structure type** — principal building vs. accessory structure vs. pool vs. screen enclosure
- **Building height** — Miami-Dade RU-4: setbacks INCREASE by 40% of additional height above 35 ft
- **Lot position** — corner lots have two "front" setbacks
- **Adjacent zone** — Miami 21: higher setbacks when abutting lower-density zones
- **Platting date** — Miami-Dade has different rules for subdivisions platted before/after March 8, 2002
- **Waterfront** — 25 ft from mean high water (no seawall) or 15 ft from seawall

### The Special Case: Miami 21 (Form-Based Code)

Miami doesn't use traditional Euclidean zoning. It uses **transect zones**:

| Zone | Density | Max Height | FAR | Character |
|------|---------|-----------|-----|-----------|
| T3 | Sub-Urban | Low | Low | Residential neighborhoods |
| T4 | General Urban | 3-5 stories | Moderate | Mixed residential |
| T5 | Urban Center | 5 stories | N/A | Mixed-use corridors |
| T6-8 | Urban Core | 8 stories | 5 | High-density, 150 du/acre |
| T6-12 | Urban Core | 12 stories | 8 | High-density, 150 du/acre |
| T6-80 | Urban Core | 80 stories | 24 | Maximum density |

**All T6 zones share the same 150 du/acre density cap** — the differentiator is height and FAR. The parsing logic for Miami 21 is fundamentally different from traditional zoning.

---

## The Agent System: Step by Step

Here's exactly how a query flows through the system:

### Step 1: Router Agent (Groq, Qwen3-4B — fast/free)

```
User: "What's the max units I can build at 123 NW 5th Ave, Fort Lauderdale?"

Router Agent thinks:
  - Intent: single_property_analysis
  - Needs: geocoding, parcel lookup, jurisdiction, zoning, ordinance, calculation
  - Plan: Property Agent → Zoning Agent → Synthesis Agent
```

### Step 2: Property Agent (Groq, Qwen3-4B)

**Tool 1: geocode_address**
- Input: "123 NW 5th Ave, Fort Lauderdale, FL"
- Provider: Geocodio (free)
- Output: `{lat: 26.1224, lng: -80.1479, normalized: "123 NW 5th Ave, Fort Lauderdale, FL 33311"}`

**Tool 2: lookup_parcel**
- Input: lat/lng coordinates
- Provider: County ArcGIS (detect county from coordinates, query appropriate endpoint)
- For Broward: query BCPA parcels endpoint with point-in-polygon
- Output: `{folio: "504201030010", lot_size_sqft: 7500, lot_width: 75, lot_depth: 100, assessed_value: 450000}`

**Tool 3: determine_jurisdiction**
- Input: lat/lng coordinates
- Provider: County ArcGIS municipal boundaries layer
- Output: `{jurisdiction: "City of Fort Lauderdale", county: "Broward", incorporated: true}`

### Step 3: Zoning Agent (Modal, Qwen3-8B — needs reasoning)

**Tool 4: get_zoning_code**
- Input: lat/lng coordinates + county
- Provider: County ArcGIS zoning layer (point-in-polygon)
- Output: `{zoning_district: "RMM-25", description: "Medium-High Density Multi-Family Residential"}`

**Tool 5: query_zoning_ordinance (RAG)**
- Input: jurisdiction="City of Fort Lauderdale", district="RMM-25"
- This is where the RAG pipeline kicks in:
  1. Query pgvector with: `municipality:fort_lauderdale AND district:RMM-25`
  2. Hybrid search (keyword "RMM-25 setback density" + semantic similarity)
  3. Rerank retrieved chunks
  4. LLM extracts structured data from the ordinance text:

```json
{
  "district": "RMM-25",
  "municipality": "Fort Lauderdale",
  "source": "ULDR Section 47-5.38",
  "setbacks": {
    "front": 25,
    "rear": 25,
    "interior_side": 10,
    "street_side": 25,
    "unit": "feet"
  },
  "max_density_per_acre": 25,
  "max_lot_coverage": 0.40,
  "max_height_ft": 55,
  "max_height_stories": 4,
  "far": 1.0,
  "min_unit_size_sqft": 750,
  "parking_per_unit": 1.5,
  "open_space_pct": 0.20
}
```

### Step 4: Synthesis Agent (Modal, Qwen3-8B)

**Tool 6: calculate_max_units (DETERMINISTIC CODE — Not LLM)**

This is the critical calculation. Maximum units = the MINIMUM of multiple independent constraints:

```python
def calculate_max_units(
    lot_size_sqft: float,
    lot_width: float,
    lot_depth: float,
    setbacks: dict,
    max_density_per_acre: float,
    max_lot_coverage: float,
    max_height_stories: int,
    far: float,
    min_unit_size_sqft: float,
    parking_per_unit: float,
) -> dict:
    """Calculate maximum allowable units from multiple constraints."""

    # Constraint 1: DENSITY
    acres = lot_size_sqft / 43_560
    units_by_density = int(acres * max_density_per_acre)

    # Constraint 2: BUILDABLE AREA (after setbacks)
    buildable_width = lot_width - setbacks["interior_side"] * 2
    buildable_depth = lot_depth - setbacks["front"] - setbacks["rear"]
    buildable_area = buildable_width * buildable_depth

    # Constraint 3: LOT COVERAGE
    max_footprint = lot_size_sqft * max_lot_coverage
    effective_footprint = min(buildable_area, max_footprint)

    # Constraint 4: FAR (Floor Area Ratio)
    max_floor_area = lot_size_sqft * far
    total_floor_area_from_footprint = effective_footprint * max_height_stories
    effective_floor_area = min(max_floor_area, total_floor_area_from_footprint)
    units_by_far = int(effective_floor_area / min_unit_size_sqft)

    # Constraint 5: PARKING
    # Assume 180 sqft per parking space (standard)
    parking_area_per_unit = parking_per_unit * 180
    # Surface parking takes from buildable area, or structured parking takes from floor area
    # Simplified: deduct parking from total floor area
    usable_floor_area = effective_floor_area * 0.85  # 15% for circulation/common
    net_floor_area = usable_floor_area - (units_by_density * parking_area_per_unit)
    units_by_parking = int(net_floor_area / min_unit_size_sqft)

    # BINDING CONSTRAINT: the minimum wins
    max_units = max(1, min(
        units_by_density,
        units_by_far,
        units_by_parking,
    ))

    binding = "density"
    if max_units == units_by_far:
        binding = "far"
    if max_units == units_by_parking:
        binding = "parking"

    return {
        "max_units": max_units,
        "binding_constraint": binding,
        "breakdown": {
            "by_density": units_by_density,
            "by_far": units_by_far,
            "by_parking": units_by_parking,
            "buildable_area_sqft": buildable_area,
            "effective_footprint_sqft": effective_footprint,
            "effective_floor_area_sqft": effective_floor_area,
        }
    }
```

**Example calculation for our Fort Lauderdale property:**
```
Lot: 7,500 sqft (75ft x 100ft)
District: RMM-25 (25 du/acre, FAR 1.0, 4 stories, 40% coverage)

By density:    (7500/43560) * 25 = 4.3 → 4 units
By FAR:        7500 * 1.0 = 7,500 sqft ÷ 750 sqft/unit = 10 units
By footprint:  75 - 20 = 55ft width, 100 - 50 = 50ft depth = 2,750 sqft
               2,750 * 4 stories = 11,000 sqft → 14 units (but FAR caps at 10)

Binding constraint: DENSITY at 4 units
```

**Tool 7: assess_deal (LLM Analysis)**
- Receives ALL context from all agents
- Provides qualitative assessment: investment viability, risks, opportunities
- This is the only step that should use LLM reasoning

---

## The RAG Pipeline: Building the Zoning Knowledge Base

This is the data engineering core of PlotLot. We need zoning ordinances for ~104 jurisdictions, parsed, chunked, and searchable.

### Phase 1: Start with 10 Priority Jurisdictions

Don't try to do all 104 at once. Start with the highest-value areas:

| # | Jurisdiction | Platform | Code Location |
|---|-------------|----------|---------------|
| 1 | Miami-Dade County (unincorporated) | eLaws/Municode | Chapter 33 |
| 2 | City of Miami | PDF (Miami 21) | miami21.org |
| 3 | City of Fort Lauderdale | eLaws/Municode | ULDR Chapter 47 |
| 4 | Broward County (unincorporated) | Municode | Chapter 39 |
| 5 | City of West Palm Beach | Encode Plus/Municode | Chapter 94 |
| 6 | Palm Beach County (unincorporated) | PDF (ULDC) | Article 3 |
| 7 | City of Hollywood | American Legal | Zoning/LDR |
| 8 | City of Coral Gables | Municode | Zoning Code |
| 9 | City of Boca Raton | Municode | Chapter 28 |
| 10 | City of Doral | Municode | Chapter 68 |

### Ingestion Pipeline

```
                 ┌─────────────────────────────────────────────┐
                 │          Zoning Ordinance Sources            │
                 │                                             │
                 │  Municode (HTML) ──┐                        │
                 │  eLaws (HTML) ─────┤                        │
                 │  American Legal ───┼── Scrapers/Parsers     │
                 │  Encode Plus ──────┤  (per-platform)        │
                 │  PDF (Miami 21) ───┘                        │
                 └──────────────────┬──────────────────────────┘
                                    │
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │          Document Processing (Ray Data)      │
                 │                                             │
                 │  1. Parse HTML/PDF → structured sections    │
                 │  2. Identify district regulations            │
                 │  3. Extract tables (setbacks, density)       │
                 │  4. Section-aware chunking                   │
                 │                                             │
                 │  Metadata per chunk:                         │
                 │    - municipality: "fort_lauderdale"         │
                 │    - county: "broward"                       │
                 │    - district: "RMM-25"                      │
                 │    - section: "dimensional_requirements"     │
                 │    - code_platform: "elaws"                  │
                 │    - last_updated: "2025-11-15"              │
                 └──────────────────┬──────────────────────────┘
                                    │
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │          Embedding + Storage                 │
                 │                                             │
                 │  BGE-M3 embedding → pgvector                │
                 │  tsvector for keyword search                 │
                 │  Structured tables for known regulations     │
                 └─────────────────────────────────────────────┘
```

### Chunking Strategy

Zoning ordinances have natural structure. Use it:

```
One chunk = one zoning district's dimensional requirements

Example chunk for Miami-Dade RU-3:
{
  "text": "Section 33-187. RU-3 Four-Unit Apartment House District.
           (a) Uses Permitted. No land, body of water and/or structure shall
           be used or permitted to be used, and no structure shall be
           hereafter erected...
           (c) Lot size. Minimum lot size: 10,000 sq ft. Minimum lot width:
           75 feet. (d) Setbacks. Front: 25 feet. Rear: 25 feet. Side: 20
           feet. Street side: 25 feet...",
  "metadata": {
    "municipality": "miami_dade_unincorporated",
    "county": "miami_dade",
    "district": "RU-3",
    "section_type": "dimensional_requirements",
    "source_url": "http://miamidade.elaws.us/code/coor_ch33_artxxiii_sec33-187",
    "last_scraped": "2026-02-01"
  }
}
```

### Hybrid Retrieval Strategy

The agent doesn't just do semantic search. It does **structured + semantic hybrid retrieval**:

```sql
-- Step 1: Filter by jurisdiction and district (exact match)
-- Step 2: Semantic search within that subset

SELECT chunk_text, metadata,
       1 - (embedding <=> query_embedding) AS semantic_score,
       ts_rank(tsvector, plainto_tsquery('setback density height')) AS keyword_score,
       (0.6 * (1 - (embedding <=> query_embedding)) +
        0.4 * ts_rank(tsvector, plainto_tsquery('setback density height'))) AS combined_score
FROM zoning_chunks
WHERE metadata->>'municipality' = 'fort_lauderdale'
  AND metadata->>'district' = 'RMM-25'
ORDER BY combined_score DESC
LIMIT 5;
```

This is dramatically more precise than naive RAG. We're not searching ALL zoning documents — we're searching the specific municipality + district combination.

---

## Structured Data Cache: The Speed Layer

For jurisdictions we've already processed, we can build a **structured lookup table** that skips RAG entirely:

```sql
CREATE TABLE zoning_regulations (
    id SERIAL PRIMARY KEY,
    municipality VARCHAR(100) NOT NULL,
    county VARCHAR(50) NOT NULL,
    district VARCHAR(50) NOT NULL,

    -- Setbacks (feet)
    front_setback FLOAT,
    rear_setback FLOAT,
    interior_side_setback FLOAT,
    street_side_setback FLOAT,

    -- Density
    max_density_per_acre FLOAT,
    min_lot_size_sqft FLOAT,
    min_lot_width FLOAT,

    -- Building envelope
    max_height_ft FLOAT,
    max_height_stories INT,
    max_lot_coverage FLOAT,
    far FLOAT,

    -- Unit requirements
    min_unit_size_sqft FLOAT,
    parking_per_unit FLOAT,
    open_space_pct FLOAT,

    -- Source
    source_section VARCHAR(200),
    source_url TEXT,
    last_verified DATE,

    -- Computed
    UNIQUE(municipality, district)
);
```

**The smart flow:**
1. Check structured cache first (instant, deterministic)
2. If cache hit → skip RAG, go straight to calculation
3. If cache miss → RAG pipeline → extract → calculate → AND cache the result for next time

This means the first query for a new district is slow (RAG + extraction). Every subsequent query for the same district is instant (structured lookup).

---

## Cost Breakdown

### Data Sources: $0/month
| Source | Cost | Notes |
|--------|------|-------|
| Geocodio | $0 | 2,500/day free tier |
| County ArcGIS (all 3) | $0 | Public endpoints, no auth |
| County Open Data Hubs | $0 | Free downloads |
| Zoning ordinance text | $0 | Public records (Municode, eLaws, city sites) |

### Compute: $0/month
| Component | Cost | Notes |
|-----------|------|-------|
| Modal (model serving + training) | $0 | $30 free credits, scales to zero |
| Groq (Router + Property Agent) | $0 | Free tier |
| PostgreSQL + pgvector (Neon) | $0 | Free tier |
| All self-hosted services | $0 | Docker Compose locally |

### Total: $0/month

The entire system — geocoding, GIS queries, zoning lookups, model serving, database — runs on free tiers.

---

## What Makes This Hard (And Why It's Valuable)

| Challenge | Why It's Hard | How We Solve It |
|-----------|---------------|-----------------|
| 104 jurisdictions | Each has its own zoning code | Start with 10 priority, RAG + structured cache scales |
| Different code platforms | Municode vs eLaws vs PDF vs American Legal | Per-platform parsers, unified chunk format |
| Miami 21 form-based code | Fundamentally different from Euclidean zoning | Separate parsing logic, transect-aware extraction |
| Setback complexity | Varies by structure type, height, adjacency, platting date | Store multiple setback rules per district, calculate worst-case |
| Multi-constraint calculation | Max units ≠ density alone | Deterministic code checking density, FAR, coverage, parking |
| Data freshness | Zoning codes change via ordinance amendments | Airflow DAG checks for updates, re-scrape on change |
| Overlay districts | Modify base zoning rules | Additional layer in RAG, compound regulation model |

**This is the problem that makes PlotLot a real ML platform project, not a toy demo.** It requires:
- Multi-source data engineering (GIS, HTML scraping, PDF parsing)
- Domain-specific RAG (structured metadata filtering + semantic search)
- Deterministic calculation (the math must be right)
- Agent orchestration (multiple agents, parallel execution)
- Fine-tuned extraction (base models aren't good at structured extraction from legal text)
- Continuous data pipeline (ordinances change)
- Production evaluation (golden dataset of verified properties)

---

## Implementation Priority

| Phase | What | Jurisdictions |
|-------|------|--------------|
| **1** | Scaffold + GIS integration + geocoding | N/A (infrastructure) |
| **2** | Miami-Dade unincorporated zoning (simplest) | 1 jurisdiction |
| **3** | RAG pipeline for Miami-Dade Chapter 33 | 1 jurisdiction |
| **4** | Multi-constraint calculation engine | 1 jurisdiction |
| **5** | Add City of Fort Lauderdale (different platform: eLaws) | 2 jurisdictions |
| **6** | Add City of Miami (Miami 21 — form-based, hardest) | 3 jurisdictions |
| **7** | Structured cache + expand to 10 jurisdictions | 10 jurisdictions |
| **8** | Fine-tune extraction model | All |
| **9** | Model serving + evaluation + full agent system | All |
| **10** | Remaining jurisdictions + overlay districts | Expanding |
