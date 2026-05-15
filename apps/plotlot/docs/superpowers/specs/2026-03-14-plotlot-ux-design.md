# PlotLot UX Quality Overhaul — Design Spec

**Date:** 2026-03-14
**Status:** Implemented

## Architecture Decision

**Approach:** Mode-driven routing with deal-type specialization

The mode toggle now controls actual routing behavior, not just cosmetic differences:
- **Lookup mode:** Structured workflow (address -> deal type -> pipeline -> tabbed report)
- **Agent mode:** Conversational with tool use badges and streaming

## Lookup Mode Design

### Flow
1. User enters address (via autocomplete or capability chip)
2. DealTypeSelector appears with 4 options
3. User selects deal type
4. Pipeline runs with narrative progress (8-step stepper)
5. TabbedReport shows with deal-type-specific hero card
6. No chat input after report — "New Analysis" button to restart

### Deal Types
| Type | Hero Metrics |
|------|-------------|
| **Land Deal** | Max Units, Max Offer (RLV), RLV/Door, Dev Margin %, Governing Constraint |
| **Wholesale** | ARV, MAO (70%), Repair Est., Assignment Fee, Comp Count |
| **Creative Finance** | Market Value, Equity Capture, LTV, Est. ARV |
| **Hybrid** | Max Units, RLV, Market Value, ARV |

### Report Structure
- **Header:** Address + confidence badge + PDF download
- **Hero Card:** Deal-type-specific metrics (highlighted amber)
- **4 Tabs:** Property | Zoning | Analysis | Deal
  - Property: ParcelViewer, zoning district quick info
  - Zoning: Dimensional standards, setbacks diagram, permitted uses, sources
  - Analysis: Density breakdown, floor plan, AI render, property intelligence
  - Deal: Comparable sales table, pro forma waterfall, document generator

## Agent Mode Design

### Enhanced Patterns (from research)
1. **Tool use badges** — Pill-shaped "Used [Tool]" badges replace vertical list
2. **Narrative pipeline** — Descriptive messages after each step completes
3. **Mode routing** — Chat falls through to conversational AI only in agent mode
4. **Follow-up suggestions** — Only shown in agent mode

## Bug Fixes

### 1. Address Autocomplete (CSS stacking context)
**Root cause:** `animate-fade-up` uses `transform`, creating stacking context. Dropdown `z-50` trapped inside form context; CapabilityChips painted on top.
**Fix:** Added `relative z-10` to form wrapper.

### 2. Parcel Boundary (silent degradation)
**Root cause:** ArcGISParcelMap shows center marker only when `parcelGeometry` is null/< 3 points, with no indication.
**Fix:** Added amber notice overlay: "Parcel boundary unavailable — showing approximate location"

### 3. AI Architectural Render (sync in async)
**Root cause:** `generate_building_image()` called synchronous `client.models.generate_content()` inside async function, blocking event loop. Model ID may be stale.
**Fix:** Changed to `await client.aio.models.generate_content()` with `gemini-2.5-flash` model. Added error logging.

### 4. Lookup Allows Chat (no mode check)
**Root cause:** `sendMessage()` had no mode guard — non-address text fell through to chat in both modes.
**Fix:** Added mode check. Lookup mode shows address prompt. Agent mode routes to chat.

## New Components

| Component | File | Purpose |
|-----------|------|---------|
| `DealTypeSelector` | `components/DealTypeSelector.tsx` | 4-card deal type picker |
| `DealHeroCard` | `components/DealHeroCard.tsx` | Deal-specific metric boxes |
| `TabbedReport` | `components/TabbedReport.tsx` | 4-tab report replacing monolithic ZoningReport |

## Modified Components

| Component | Changes |
|-----------|---------|
| `page.tsx` | Deal type state, lookup flow, mode routing, TabbedReport integration |
| `AnalysisStream.tsx` | Narrative descriptions, completion messages |
| `ArcGISParcelMap.tsx` | Missing geometry indicator |
| `CapabilityChips.tsx` | Lookup chips are address-only |
| `render.py` | Async Gemini client, model update |

## Patterns Adopted (from Phase 1 Research)

| # | Pattern | Source | Implementation |
|---|---------|--------|----------------|
| 1 | Mode toggle controls routing | Z.ai | Lookup = pipeline only, Agent = chat |
| 2 | Deal type cards | Original | DealTypeSelector with 4 strategy options |
| 3 | Tool use badges | ChatGPT | Pill badges: "Used Geocoding", "Used Zoning Search" |
| 4 | Narrative between steps | ChatGPT | "Found property in Miramar...", "Retrieved record: Folio..." |
| 5 | Report tabs | ChatGPT Canvas | 4-tab structure (Property, Zoning, Analysis, Deal) |
| 6 | Hero card per strategy | Original | Deal-type-specific metric highlights |
| 7 | No chat in lookup | Z.ai | Input bar hidden after report, "New Analysis" to restart |
