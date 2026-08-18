# Per-city zoning registry — task list and verification recipe

Written 2026-08-12. Updated 2026-08-13. Pick this up cold; everything needed is here.

> **Status 2026-08-13: 3 of 7 cities deterministic** — San Diego, **Escondido**,
> **Oceanside**. Four remain (Encinitas, El Cajon, Chula Vista, Poway). The two
> completed sections below carry corrections to this document's own assumptions;
> read them before starting city #4.

## Why this exists

`max_units` was deterministic **for the City of San Diego only** — 7 units on
1233 Hueneme, `origin=local_authority`, 5/5 identical runs. Every other city
re-derived density from an LLM on every run and could flip between answers.

The reason is a broken join, not missing data. A dimensional standard is keyed on
**(municipality, district_code)**, and only San Diego parcels come back with a
`district_code`:

| City | parcel `zoning_code` | stored standards | reachable? |
|---|---|---:|---|
| San Diego | `RM-3-7` | 34 | **yes** |
| Escondido | *(empty)* | 10 | no |
| Encinitas | *(empty)* | 10 | no |
| El Cajon | *(empty)* | 10 | no |
| Oceanside | *(empty)* | 8 | no |
| Chula Vista | *(empty)* | 4 | no |
| Poway | *(empty)* | 4 | no |

**46 validated districts are already in the database and unreachable.** They are
correct and cost nothing; they light up the moment a zone code exists. Closing this
join activates six cities at once and is worth more than any further extraction work.

San Diego works because `california.py`'s `"san diego"` county config sets
`zoning_url` to the *City of San Diego's* citywide layer. That slot is per-county,
so it can only ever serve one city. The other cities each publish their own layer.

## The shape of the fix

A **curated registry**, not auto-discovery. Auto-discovery was tried and fails in
two specific ways documented under Traps — it returns overlay layers and misses
known-good services. Model it on `property/marin_zoning.py`, which already does
per-city point-in-polygon zoning for Marin, and hook it in beside
`_enrich_marin_zoning` in `california.py` (~line 326).

```python
# property/san_diego_zoning.py
_SD_CITY_ZONING = {
    "escondido": CityZoning(
        url="https://services2.arcgis.com/eJcVbjTyyZIzZ5Ye/arcgis/rest/services/Zoning/FeatureServer/0",
        zone_field="ZONING",
        verified_at="1234 E Valley Pkwy",   # returns S-P
    ),
    ...
}
```

Each entry is only added **after** the recipe below passes for that city.

## Verification recipe (run per city)

A registry entry that has not passed all five steps must not be committed. A wrong
zone code is worse than no zone code: it silently selects another district's
standard and produces a confidently wrong unit count, which is the exact failure
this whole effort removed.

**1. Find candidate services.** ArcGIS Hub, then the city's own GIS host:

```bash
curl -s "https://hub.arcgis.com/api/v3/datasets?q=<CITY>+zoning&filter\[type\]=Feature+Service&page\[size\]=8" \
  | python -c "import json,sys; [print(d['attributes'].get('name'),'|',d['attributes'].get('url')) for d in json.load(sys.stdin)['data']]"
```

Also try `gis.<city>ca.org` / `<city>ca.gov` directly — Oceanside is on
`gis.oceansideca.org`, not Hub.

**2. Enumerate the layers and pick the BASE district layer deliberately.**

```bash
curl -s "<FeatureServer URL>?f=json" | python -c "import json,sys; [print(l['id'], l['name']) for l in json.load(sys.stdin)['layers']]"
```

Do not take the first layer that returns a feature. Oceanside's Planning_Hub layer
12 is the *Coastal overlay*; the base districts are a different layer.

**3. Query at a RESIDENTIAL address, never a civic one.** Use the project's own
helper so the test matches production exactly:

```python
from plotlot.property.arcgis_utils import spatial_query
feats = await spatial_query(f"{layer_url}/query", lat, lng)
print(feats[0]["attributes"])
```

**4. Check the returned code against the stored districts for that city** (listed
below). A layer whose codes do not appear there is either the wrong layer or needs
a crosswalk — resolve which before proceeding.

**5. Prove the whole chain end-to-end**, not just the layer:

```python
pr = await lookup_property(addr, county, lat, lng, state="CA")
assert pr.zoning_code                                    # step 1: code resolves
std = await get_dimensional_standard(city, pr.zoning_code)
assert std is not None                                   # step 2: standard joins
rep = await lookup_address(full_address)
assert rep.density_analysis.origin == "local_authority"  # step 3: deterministic path
```

Then run it **5 times with `lookup._pipeline_cache.clear()`** between runs and
confirm `max_units` is identical every time. Determinism is the deliverable; a
single passing run proves nothing (see the scratchpad `determinism_check.py`
pattern used for San Diego).

## Traps — all three cost real time already

**Zoning gaps swallow the query point.** `500 N Broadway, Escondido` returns **0
features**, and moving the point **0.4 m** flipped it from `S-P` to nothing. Civic
buildings and street-centerline geocodes fall outside zoning polygons. Test with
residential addresses. Note `pr.lat/lng` from the CA provider merely echo the
geocode — a true parcel centroid must be derived from `parcel_geometry` if a
fallback nudge is needed.

**Overlay layers answer first.** See step 2.

**Returned codes are not ordinance district codes.** *(Overstated — see Escondido
below: measured across the whole layer, 29.1% of its polygons match a stored
district verbatim and no crosswalk was needed. Establish the code domain before
concluding this.)* Escondido's layer returns `S-P` (Specific Plan) at a civic
address while its stored districts are `R-1-6`…`R-1-25`. The seam for
this already exists — `retrieval/zoning_crosswalk.py` / `crosswalk_zoning_code`,
already called in `lookup.py` before the GIS code. Each city's mapping needs
verifying, and codes with no ordinance equivalent (Specific Plan, PD, overlays)
must resolve to **no district** rather than a guess.

## Per-city task list

Ordered by value: chunk count × how tractable the layer looked.

### 1. Escondido — ✅ DONE 2026-08-13 (`property/san_diego_zoning.py`)
- **URL** `https://services2.arcgis.com/eJcVbjTyyZIzZ5Ye/arcgis/rest/services/Zoning/FeatureServer/0`
- **Field** `ZONING` (the layer also carries `APN`). Layer 3 is *Split Zoning* — not consulted.
- All five steps pass. 5/5 cache-cleared runs on 616 Carlann Ln returned
  `max_units=1`, `origin=local_authority`, `governing=min_lot_area`
  (lot 6,300 ÷ R-1-6's 6,000 sqft-per-unit).
- Stored: `R-1-6 · R-1-7 · R-1-8 · R-1-9 · R-1-10 · R-1-12 · R-1-15 · R-1-18 · R-1-20 · R-1-25` (sqft/unit = the suffix × 1,000)

**Two things this plan got wrong — check them on every remaining city.**

**No crosswalk was needed.** This plan said the layer "returns `S-P` while its
stored districts are `R-1-6`…" and concluded a crosswalk was required. That was
measured at *one civic address*, which is the trap this document itself warns
about. Across the whole layer the codes match verbatim: **13,773 of 47,331
polygons (29.1%) are an exact stored district.** Establish the code *domain*
(`returnDistinctValues=true`, then a `groupByFieldsForStatistics` count) before
concluding anything from a single point.

**The municipality name is not a usable key.** San Diego County is configured
against the CA statewide parcel layer, and `_spatial_parcel`'s municipality
fallback chain did not read that layer's `SITE_CITY` field — so every SD parcel
arrived with `municipality=""` and a name-keyed registry never fired at all.
Fixed by adding `SITE_CITY` to the chain (this populates municipality for all of
SD county, which is also the ordinance-search join key), **and** by making the
resolver fall back to a concurrent geometry fan-out when the name is absent.
City layers do not overlap, so geometry is the reliable discriminator; two
cities claiming one point returns no district rather than a guess.

**Match exactly — never by substring.** Three live shapes each contain or
resemble a valid district and must be refused:
`PZ-*` (pre-zoned for annexation, **county** authority today — `PZ-R-1-10`, 56
polygons), `A/B` composites (split-zoned — `R-1-10/RE-20`, 142 polygons), and
`COUNTY` (8,747 polygons, the layer's single largest value).

**The remaining Escondido gap is extraction, not the join.** `R-T` (3,462),
`RE-20` (2,989), `R-2-12` (2,750) and `R-3-18` (1,924) are real districts with
**no stored standard**. They now resolve a district and correctly miss the join.

### 2. Oceanside — ✅ DONE 2026-08-13
- **Layer 11** `.../WebService/Planning_Hub/FeatureServer/11` (`ZONING`).
  Layer 12 is *Preserve Planning Zones*, not the coastal overlay this plan
  assumed; the coastal boundary is layer 2.
- **Field `Zone_Code`, NOT `Zone_Code_Print`.** Both exist. The printed form
  appends the overlay (`RS` → `RS-SP`, `RE-B` → `RE-B-EQ`) and would miss the
  standards join on every overlaid parcel — which is most of them. Overlays are
  separately available in `Overlay1`/`Overlay2`. No `/CZ` variants appear in the
  bare field, so the coastal concern below was unfounded.
- All 8 stored districts appear verbatim. They cover **12,514 of 32,002 zoned
  acres (39.1%)**. Note this layer is dissolved zone polygons (607 of them), not
  parcels — so acres, not polygon count, is the honest coverage metric here.
- Stored: `RE-A 0.5 · RE-B 1 · RS 3.6 · RM-A 6 · RM-B 10 · RM-C 15.1 · RH 21 · RH-U 29` (du/acre)
- **Verified deterministic on the APN path** (`1461216100`): 5/5 cache-cleared
  runs, `origin=local_authority`, `zone=RE-B`. Getting there required the two
  fixes below, neither of which had anything to do with Oceanside.
- **Open question, not a bug:** that parcel returns `max_units=0` — 8,980 sqft is
  0.206 acres, and 0.206 x 1 du/acre floors to 0. Arithmetically right for the
  density rule. Whether Oceanside grants one dwelling right on a legally-created
  substandard lot is a *separate ordinance provision we have not extracted*. Do
  not "fix" this by rounding up; extract the nonconforming-lot rule.
- **This layer also publishes dimensional standards directly** (`Height`,
  `Front_Setb`, `Min_Lot_Si`, `Density`, `Lot_Covera`…). Tempting as a second
  source, but it is GIS-published rather than ordinance text, and the values are
  dirty (`Min_Lot_Si` reads `"10, 000 sq. ft."`). It would be assumption-grade —
  `STAGED` at best, never `VERIFIED` — so it is deliberately not used.

### Two bugs found while wiring Oceanside — both city-agnostic

Neither is an Oceanside problem. Both were blocking *every* city; Escondido only
escaped them by accident of how it was tested.

**1. The APN path resolved no zoning at all.** `lookup_by_apn` returned the parcel
straight after the assessor lot override — no step-2 spatial query, no city
fallback — so an APN-identified parcel had an empty district for every city,
including the City of San Diego whose citywide layer is configured. Its docstring
claimed "so slope and zoning still work"; only the geometry did. Escondido passed
because it was verified with an *address*, which takes the other branch. Both
paths now share one zoning resolution.

**2. The standards join was case-sensitive.** `get_dimensional_standard` compared
`municipality` exactly. Casing is not ours to control: an address-resolved parcel
gets `"Oceanside"` from the geocoder, an APN-resolved one gets `"OCEANSIDE"` from
the parcel layer's `SITE_CITY`. The second silently missed — **the standard was
present, verified, and unreachable** — so density fell back to the LLM and the
same parcel returned 0 units on one run and 8 on the next. The fixture fallback
had documented case-insensitive matching all along, so the primary source was
stricter than its own fallback. Both keys are now compared lowered.

**The lesson for city #3 onward: verify through both an address and an APN.**
They take different code paths and read municipality from different fields. A
city that passes one can fail the other — which is exactly what Escondido's
"5/5 deterministic" hid.

### 3. Encinitas — not yet found
- Stored: `RR-1 1 · RR-2 2 · R-3 3 · R-5 5 · R-8 8 · RS-11 11 · R-15 15 · R-20 20 · R-25 25 · R-30 30` (du/acre)

### 4. El Cajon — not yet found
- Stored: `RS-40 40,000 · RS-20 20,000 · RS-14 14,000 · RS-9 9,000 · RS-6 6,000 · RM-6000 6,000 · RM-4300 4,300 · RM-2500 2,500 · RM-2200 2,200 · RM-1450 1,450` (sqft/unit)

### 5. Chula Vista — not yet found
- Stored: `R-1-5 5,000 · R-1-7 7,000 · R-1-10 10,000 · R-1-15 15,000` (sqft/unit)

### 6. Poway — not yet found
- Stored: `RS-2 2 · RS-3 3 · RS-4 4 · RS-7 8` (du/acre — RS-7 really is 8, confirmed against §17.08.060)

## Definition of done

**Per city:** a registry entry whose five recipe steps pass, plus a test asserting
the crosswalk maps that city's real GIS codes to its stored district codes.

**Overall:** `plotlot-standards --check` still reports honestly, and a parcel in
each wired city returns `origin=local_authority` with a stable `max_units` across
five cache-cleared runs.

**Do not** wire a city whose codes you could not match to stored districts. Leaving
`zoning_status: not_determined` is the correct, honest outcome — the pipeline
already handles it and marks the count provisional.

## Also worth knowing

- SanGIS PDS layers 3/7/13 cover **unincorporated county only** (0 features for
  Oceanside parcels). A regional layer will not solve this; it has to be per-city.
- **Carlsbad is out of scope and cannot be fixed this way** — its minimum lot area
  is keyed on the General Plan land use designation, so one zone code carries three
  different answers. It needs the designation layer as a *second* join. Details in
  the `ingestion/standards_extraction.py` module docstring.
- National City and San Marcos have no stored standards yet for a different reason:
  the chunker flattens their dimensional tables to positional columns
  (`Minimum lot area — 1: 15,000 SF; 2: 5,000 SF`), losing the district header.
  That is an upstream chunking fix, independent of this work.
