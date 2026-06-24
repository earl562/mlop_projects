# PlotLot Core Enhancement Plan

## Source: Daniil Kleyman's Development Training Transcripts
4 transcripts analyzed: build-to-rent-eval.txt, 31-unit-case-study.txt, fund-deals-easy.txt, how-to-fund-dev.txt

---

## Current State

PlotLot's pipeline: `geocode → property → zoning → LLM → calculator → comps → proforma`

### What Works
- Step 1 (Zoning & Unit Mix): calculator.py computes max_units (4 constraints) and max_gla for commercial
- Property type routing: residential → calculate_max_units(), commercial → calculate_max_gla()
- Pipeline streaming: SSE events, progressive disclosure
- Frontend: workspace renders, sidebar functional, address input

### What's Broken
- **Comps inconsistency**: HasData returns wrong-city results when municipality field is "FL" → FIXED with _resolve_search_city()
- **Cache inconsistency**: Same address with different format ("FL" vs "Florida") → different cache keys → different results → FIXED with normalize_address() state abbreviation expansion
- **ADV from land comps, not new-build**: Proforma uses land sale price/bedroom = ADV per unit, producing absurdly low values ($138K in Miami)
- **No rental comps**: Can't compute NOI (Dani's Step 3)
- **No financing analysis**: No DSCR, LTV, max leverage (Dani's Steps 4-7)
- **No deal metrics**: No cash-on-cash, sweat equity (Dani's Step 8)

---

## Dani's 10-Step Underwriting Framework (Target State)

### Step 1: Zoning & Unit Mix ✅ EXISTING
What can you build? Zoning → max units/GLA → setbacks → permitted uses

### Step 2: As-Built Value ❌ MISSING
What's the finished property worth?
- ≤4 units: new-construction sales comps ($/sqft)
- \>4 units: NOI / cap_rate
- Commercial: GLA × market rent / cap_rate

### Step 3: Proforma NOI ❌ MISSING
- Rental comps per unit type (HUD Fair Market Rents API — free)
- Unit mix distribution
- OpEx ratio: 30% duplex, 35-40% multifamily
- NOI = Gross Income × (1 - OpEx%)

### Step 4: Max Leverage ❌ MISSING
- DSCR = NOI / Debt Service ≥ 1.25
- Max monthly payment = NOI / 1.25
- Solve PMT backward for max loan principal
- Permanent financing FIRST, then construction mirrors it

### Step 5: Land + Construction Costs ⚠️ PARTIAL
- Land: from comps or user input
- Hard costs: construction $/sqft by county
- Soft costs: % of hard costs
- Developer fee: 8% (MISSING)
- Financing costs: origination + closing

### Step 6: Cash Required ❌ MISSING
- Total cost - max construction loan = equity needed
- Construction LTC: 65-75%

### Step 7: Short-Term Financing ❌ MISSING
- Interest carry during construction (interest-only, 12-18 months)
- Avg outstanding balance ~60% of loan
- Construction → permanent auto-rollover (single close)

### Step 8: Evaluate KPIs ❌ MISSING
- Cash-on-Cash % = (NOI - debt) × 12 / cash_invested
- Sweat Equity % = (ABV - total cost) / ABV
- Imputed Land Equity = market value - purchase price
- Thresholds: CoC ≥ 10% = strong go, ≥ 7% = go, < 7% = no-go
- Sweat Equity ≥ 30% = strong go

### Step 9: Adjust Levers ❌ MISSING
- Reverse proforma: given land price → required ADV for target CoC
- Sensitivity: land price, amortization, interest rates

### Step 10: Go/No-Go ❌ MISSING
- Traffic light verdict: 🟢 GO / 🟡 CONDITIONAL / 🔴 NO-GO
- Decision summary with rationale

---

## Implementation Plan (6 Waves, 12 Tasks)

### File Inventory

**New Files (11):**
1. `src/plotlot/core/types.py` — Extend with DealAnalysis, DealMetrics, FinancingTerms, CapitalStack, ProformaNOI, RentalComp, RentalCompSet, UnitMixEntry (MODIFY)
2. `src/plotlot/pipeline/rental_comps.py` — HUD FMR API client + default_unit_mix()
3. `src/plotlot/pipeline/financing.py` — Amortization, DSCR, max leverage, capital stack
4. `src/plotlot/pipeline/deal_metrics.py` — CoC, sweat equity, Go/No-Go
5. `src/plotlot/pipeline/deal_analysis.py` — Steps 2-10 orchestrator
6. `src/plotlot/api/schemas.py` — DealAnalysisResponse, DealMetricsResponse (MODIFY)
7. `src/plotlot/api/routes.py` — SSE events for deal analysis steps (MODIFY)
8. `src/plotlot/pipeline/lookup.py` — Wire Phase 6 deal analysis (MODIFY)
9. `frontend/src/components/DealDashboard.tsx` — Structured deal analysis layout
10. `frontend/src/app/(workspace)/workspace/page.tsx` — Deal analysis tab (MODIFY)
11. `frontend/src/lib/api.ts` — DealAnalysisData TypeScript interfaces (MODIFY)

### Wave 1 — Types + Skill (parallel)
- T1: core/types.py — Add 9 new dataclasses + extend ZoningReport
- T10: skills/playwright-comps/SKILL.md — Playwright browser agent for Zillow

### Wave 2 — Pure Functions (parallel, after Wave 1)
- T2: pipeline/rental_comps.py — HUD FMR API + default_unit_mix()
- T3: pipeline/financing.py — Amortization, max leverage, capital stack
- T4: pipeline/deal_metrics.py — CoC, sweat equity, Go/No-Go

### Wave 3 — Pipeline & API (parallel, after Wave 2)
- T5: pipeline/deal_analysis.py — Steps 2-10 orchestrator
- T6: api/schemas.py + routes.py — SSE events + response schemas

### Wave 4 — Frontend + Backend Wire (parallel, after Wave 3)
- T7: pipeline/lookup.py — Wire deal analysis after proforma
- T8: frontend/src/components/DealDashboard.tsx — Deal metrics display

### Wave 5 — UI Integration (sequential, after Wave 4)
- T9: workspace/page.tsx — Add deal analysis tab

### Wave 6 — QA
- T12: Integration E2E testing

---

## Dependency Graph

```
Wave 1: T1 ──────────────────────┐
                                  │
Wave 2: T2 ←── T1 ──→ T3 ──→ T4  │
                                  │
Wave 3: T5 ←── T2,T3,T4 ──→ T6   │
                                  │
Wave 4: T7 ←── T5,T6 │  T8 ←── T6│
                                  │
Wave 5: T9 ←── T7,T8              │
                                  │
Wave 6: T12 ←── T9                │
```

---

## Key Technical Decisions

1. **Rental comps source**: HUD Fair Market Rents API (free, 1200 req/min, county-level, requires free API token registration at huduser.gov)
2. **Comps backup**: HasData Zillow API (current) + Playwright browser agent (post-demo)
3. **Cache normalization**: State abbreviations expanded ("FL" ↔ "Florida") for deterministic cache keys
4. **Commercial properties**: GLA-based (different from residential units-based), no unit mix
5. **SSE streaming**: New events — rental_comps, financing, deal_metrics, deal_decision
6. **Frontend**: DealDashboard with traffic-light verdict, CoC/sweat equity gauges, expandable capital stack

---

## Known Issues & Fixes Applied

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Wrong-city comps (GA instead of FL) | municipality="FL" → HasData searches "FL, FL" | `_resolve_search_city()` falls back to county name |
| Inconsistent results for same address | Cache key varies by input format ("FL" vs "Florida") | `normalize_address()` expands state abbreviations |
| Property lookup returns wrong parcel | Spatial fallback returns nearest parcel by proximity | Spatial fallback now scores by address similarity |
| ADV absurdly low ($138K in Miami) | ADV from land comps (price/bedrooms) instead of new-build sales | Steps 2-3 will fix with rental comps + NOI approach |

---

## Demo Addresses

| Address | Type | Zoning | Key Metric |
|---------|------|--------|------------|
| 100 E Broward Blvd, Fort Lauderdale, FL 33301 | Commercial | RAC-CC | Max GLA: 48,516 sqft |
| 409 NW 2nd Way, Deerfield Beach, FL 33441 | Residential | RS-5 | Lot too small for density (6,600 sqft) |
| 171 NE 209th Ter, Miami, FL 33179 | Residential | R-1 | Max units: 1, 7,500 sqft lot |

---

*Plan generated from: 48 Daniil Kleyman training transcripts + plotlot codebase audit*
*Last updated: 2026-06-18*
