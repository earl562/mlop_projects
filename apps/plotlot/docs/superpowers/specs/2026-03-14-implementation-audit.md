# PlotLot UX Quality Overhaul — Implementation Audit

**Date:** 2026-03-14
**Auditor:** Architecture Review
**Branch:** `feat/land-deal-intelligence-platform`
**Status:** Partial Implementation — Frontend scaffolding done, backend untouched

---

## Section 1: Executive Summary

**Goal:** Transform PlotLot from a single-pipeline zoning tool into a deal-type-aware intelligence platform with distinct Lookup and Agent modes, four deal types with strategy-specific hero cards, a tabbed report structure, and 12 UX patterns adopted from Z.ai, ChatGPT, Gemini, and MiniMax.

**What was accomplished:**
- Three new frontend components created: `DealTypeSelector`, `DealHeroCard`, `TabbedReport`
- Lookup mode now shows a deal type selector after address entry
- A tabbed report (Property / Zoning / Analysis / Deal) replaces the monolithic `ZoningReport` for lookup mode
- Deal-type-specific hero cards display different metrics per strategy
- Four bugs were fixed (autocomplete z-index, parcel boundary indicator, AI render async, lookup-blocks-chat)
- `AnalysisStream` gained narrative descriptions and step completion messages
- `CapabilityChips` were differentiated by mode (addresses for Lookup, tool launchers for Agent)
- Design spec and research spec were written

**What is the gap:**
- Zero backend changes. No `scope` parameter, no deal-type-aware pipeline, no intent parsing, no thinking/artifact SSE events.
- The deal type selector is purely cosmetic — selecting "Wholesale" vs "Land Deal" runs the exact same 8-step pipeline and returns the exact same data. The hero card just slices/recalculates the same report differently.
- Agent mode has no new capabilities — no thinking transparency, no artifact cards, no pipeline plan approval, no enhanced tool use. The chat.py file is unchanged.
- No per-claim citations. No scoped pipeline execution. No `quick`/`standard`/`full` pipeline modes.
- No tests were written for the new components.

---

## Section 2: Phase-by-Phase Scorecard

### Phase 1: Install Tools + Research
**Rating:** Done (pre-existing)

This phase was completed before this work began. Research was synthesized into the spec at `2026-03-14-agent-ux-research.md`.

### Phase 2: Design PlotLot UX
**Rating:** Done

Two spec documents were produced:
- `2026-03-14-agent-ux-research.md` — 12-pattern research synthesis
- `2026-03-14-plotlot-ux-design.md` — Implementation design spec

The specs are well-structured with clear architecture decisions, component plans, and pattern mappings. The design spec accurately documents what was built. However, it also retroactively marks some patterns as "implemented" that are only partially done (e.g., Pattern 2 "Tool cards in Agent mode" is listed as adopted, but agent mode capability chips are static prompts, not functional tool launchers).

### Phase 3: Fix 4 Bugs
**Rating:** Done

All four bugs were fixed:

| Bug | Fix | Verified |
|-----|-----|----------|
| Autocomplete dropdown trapped under chips | Added `relative z-10` to form wrapper in `page.tsx` | Yes — line 401 |
| Parcel boundary silent failure | Added amber notice overlay in `ArcGISParcelMap.tsx` | Yes — lines 369-378 |
| AI Render sync-in-async | Changed to `await client.aio.models.generate_content()` in `render.py` | Yes — line 269 |
| Lookup allows chat | Added mode guard in `sendMessage()` in `page.tsx` | Yes — lines 219-226, 229-234 |

### Phase 4: Lookup Mode Redesign
**Rating:** Partial

**Done:**
- `DealTypeSelector` component with 4 deal types (Land Deal, Wholesale, Creative Finance, Hybrid) with icons, descriptions, and metric previews
- `DealHeroCard` with 4 strategy-specific metric layouts
- `TabbedReport` with 4 tabs (Property, Zoning, Analysis, Deal) properly organized
- Flow: address -> deal type selector -> pipeline -> tabbed report
- Input bar hidden after report in lookup mode ("New Analysis" to restart)
- Narrative pipeline step descriptions in `AnalysisStream`

**Not done:**
- Pipeline scoping. The `streamAnalysis` function signature is `streamAnalysis(address, onStatus, onResult, onError)` — no deal type or scope parameter. `AnalyzeRequest` in `schemas.py` has only an `address` field. The backend always runs all 8 steps regardless of deal type.
- Smart section defaults (all sections collapsed except hero). The tabs default to "property" open, not a deal-type-specific default.
- Scope inference from input content ("just zoning" -> quick, "full analysis" -> full). Not implemented at all.

### Phase 5: Agent Mode Redesign
**Rating:** Not Done

`chat.py` has zero changes related to the UX overhaul. Specifically:
- No intent parsing or auto-tool-selection
- No `thinking` SSE event type
- No `artifact` SSE event type for document generation
- No pipeline plan approval ("I'll analyze X. Skip any?")
- No enhanced tool use badges (the existing tool_use/tool_done SSE events from the prior implementation are displayed in the frontend, but this was pre-existing, not part of this overhaul)
- The `CapabilityChips` for agent mode are updated to show "Analyze Property", "Generate Documents", etc. but these are static prompt strings, not functional tool launchers that trigger specific backend tools.

### Phase 6: Quality Testing
**Rating:** Not Done

- No test files were created for `DealTypeSelector`, `DealHeroCard`, or `TabbedReport`
- No Playwright tests for the new lookup flow
- No unit tests for deal-type metric calculations in `DealHeroCard`
- No regression tests for the 4 bug fixes
- The existing `uat.spec.ts` was not updated to cover the new flow

### Phase 7: Merge & Deploy
**Rating:** Not Done

The changes are on `feat/land-deal-intelligence-platform` branch with uncommitted changes. No PR created, no merge, no deploy.

---

## Section 3: Pattern Adoption Scorecard

| # | Pattern | Source | Rating | Assessment |
|---|---------|--------|--------|------------|
| 1 | Mode toggle controls routing | Z.ai | Done | `sendMessage()` now checks `mode` state. Lookup rejects non-addresses. Agent falls through to chat. This is the most complete pattern. |
| 2 | Tool cards in Agent mode | Z.ai | Partial | `CapabilityChips` shows "Analyze Property", "Generate Documents" etc. in agent mode, but these are pre-filled prompt strings, not actual tool launchers that invoke specific backend capabilities. They just paste text into the input. |
| 3 | Agent auto-selects tools | ChatGPT | Not Done | No intent parsing in `chat.py`. Agent uses the same pre-existing tool schema. No changes to how the agent decides which tools to call. |
| 4 | Tool use badges | ChatGPT | Pre-existing | The pill-shaped "Used Geocoding" / "Used Zoning Search" badges in `page.tsx` (lines 529-558) were part of the prior implementation. The frontend renders `toolActivity` from SSE `tool_use`/`tool_done` events that already existed in `chat.py`. No new work here. |
| 5 | Inline citations | ChatGPT, Gemini | Not Done | No `source_refs` field added to `NumericZoningParams`. No per-parameter citation mapping. The "View X sources" section in `TabbedReport` (lines 303-319) shows sources as a flat list, not linked to specific parameters. |
| 6 | Canvas/split panel for docs | ChatGPT, Gemini | Not Done | No split panel. `DocumentGenerator` exists in the Deal tab but is the same component as before, not a side panel. |
| 7 | Pipeline approval gate | Gemini Deep Research | Not Done | No `PipelinePlanCard` component. No "I'll analyze X. Skip any?" flow. |
| 8 | Thinking transparency | Z.ai, Gemini | Not Done | No `thinking` SSE event type in `chat.py`. No collapsible reasoning section in the frontend. The existing "Thinking..." text in `page.tsx` (line 609) is just a loading indicator, not streamed reasoning. |
| 9 | Narrative between steps | ChatGPT | Done | `AnalysisStream.tsx` has `STEP_NARRATIVES` (lines 30-38) that show contextual messages like "Found property in Miramar" and "Retrieved record: Folio 1234, 8,000 sqft" after each step completes. Also `STEP_DESCRIPTIONS` for active steps. |
| 10 | Artifact-first agent output | Z.ai | Not Done | No `ArtifactCard` component. No `artifact` SSE event type. Document generation still produces chat messages, not styled download cards. |
| 11 | 4-phase progress indicators | MiniMax | Done | `AnalysisStream` has an 8-step stepper with progress bar, percentage, time estimates, and numbered circles. This is more detailed than MiniMax's 4 phases. |
| 12 | Capability-first navigation | MiniMax | Partial | The deal type selector is a form of capability-first navigation for lookup mode, but it doesn't change what pipeline steps run. The spec envisioned "Quick Zoning, Full Deal, Comp Search, Investment Memo" as sharper capability modes, which is closer to scope-driven pipelines. The deal type selector is a step in that direction but without backend support. |

**Summary:** 3 fully implemented, 2 partial, 1 pre-existing (not new work), 6 not implemented.

---

## Section 4: Deal Type Hero Card Audit

### Land Deal
| Metric | Planned | Implemented | Match? |
|--------|---------|-------------|--------|
| Max Units | Yes | Yes | Yes |
| Max Offer | Yes | Yes (labeled "Max Offer (RLV)") | Yes |
| RLV/Door | Yes (in plan) | Yes (computed as maxOffer/maxUnits) | Yes |
| Dev Margin % | Yes | Yes (computed from GDV - total cost) | Yes |
| Governing Constraint | Yes | Yes | Yes |

**Verdict:** Matches spec. The calculations are correct — RLV/Door and Dev Margin are computed client-side from the report data.

### Wholesale
| Metric | Planned | Implemented | Match? |
|--------|---------|-------------|--------|
| ARV | Yes | Yes (uses `adv_per_unit` or `estimated_land_value`) | Mismatch |
| MAO (70% rule) | Yes | Yes (ARV * 0.7) | Synthetic |
| Repair Estimate | Yes | Yes (ARV * 0.1) | Synthetic |
| Assignment Fee | Yes | Yes (min(ARV * 0.05, $15K)) | Synthetic |
| Comp DOM | Yes (in plan) | No — shows "Comp Count" instead | Mismatch |

**Verdict:** Partially matches. The critical issue is that ARV uses `adv_per_unit` (which is "appraised development value per unit" from the land pro forma pipeline), not actual After-Repair-Value from comps. MAO, repair estimate, and assignment fee are all synthetic calculations based on this misused field. There is no actual wholesale-specific data pipeline. "Comp DOM" (Days on Market) from the plan was replaced with "Comp Count" — a lesser metric.

### Creative Finance
| Metric | Planned | Implemented | Match? |
|--------|---------|-------------|--------|
| Rate Spread | Yes | No | Missing |
| Equity Capture | Yes | Yes (ARV - Market Value) | Yes |
| Monthly Cash Flow | Yes | No | Missing |
| LTV | Yes | Yes (Market Value / ARV * 100) | Yes |
| Yield | Yes | No — shows "Est. ARV" instead | Missing |

**Verdict:** Significant gap. Rate Spread and Monthly Cash Flow are missing entirely — these require mortgage/existing loan data that the pipeline does not collect. The hero card shows Market Value and Est. ARV as substitutes, which are not creative finance metrics. The component has a comment on line 74: "Placeholder calculations — these would be real with user inputs."

### Hybrid
| Metric | Planned | Implemented | Match? |
|--------|---------|-------------|--------|
| Blended Rate | Yes | No — shows "Max Units" | Missing |
| Cash to Close | Yes | No — shows "RLV" | Missing |
| Combined Cash Flow | Yes | No — shows "Market Value" | Missing |
| Total Equity | Yes | No — shows "ARV" | Missing |
| Exit Paths | Yes | No | Missing |

**Verdict:** Does not match spec at all. The hybrid hero card shows a generic mix of land deal and property metrics. None of the planned hybrid-specific metrics (Blended Rate, Cash to Close, Combined Cash Flow, Total Equity, Exit Paths) are implemented because the backend has no hybrid deal analysis capability.

**Overall Hero Card Assessment:** Land Deal is the only deal type with real data backing. Wholesale uses synthetic approximations. Creative Finance and Hybrid are placeholder cards that display generic property data dressed up with strategy-specific labels.

---

## Section 5: What Went Well

1. **Bug fixes were thorough.** All four bugs were correctly diagnosed (root cause documented in the spec) and fixed with minimal code changes. The autocomplete z-index fix is clean. The parcel boundary notice is user-friendly. The render.py async fix is the right approach. The mode guard logic is correct.

2. **TabbedReport component is well-structured.** The 4-tab layout (Property, Zoning, Analysis, Deal) is a genuine improvement over the 579-line monolithic `ZoningReport`. Tab content is organized logically. Accessibility attributes (role="tablist", aria-selected, aria-controls) are correct.

3. **DealTypeSelector UX is polished.** The 4-card grid with icons, descriptions, and metric preview tags is clean. The responsive layout (2-col mobile, 4-col desktop) works. The hover/active states follow the design system. Accessibility labels are present.

4. **Narrative pipeline steps add real value.** The `STEP_NARRATIVES` in `AnalysisStream` that show "Found property in Miramar" and "Retrieved record: Folio 1234, 8,000 sqft" make the pipeline feel intelligent rather than mechanical. The property confirmation card with "Not the right property?" is a thoughtful touch.

5. **Mode routing in page.tsx is correct.** The `sendMessage` function properly branches on `mode` state. Lookup mode rejects non-addresses with a helpful message. The flow of address -> deal type selector -> pipeline -> report -> no-more-input is clean and prevents the "lookup allows chat" anti-pattern.

6. **Research and spec quality.** The 12-pattern research synthesis (`agent-ux-research.md`) is thorough and actionable. Each pattern has a clear source, priority, and file-level implementation plan. The design spec accurately documents the architecture decisions.

---

## Section 6: What Missed the Mark

### 1. Zero Backend Changes
The research spec explicitly called for backend modifications in `schemas.py`, `routes.py`, `chat.py`, and `core/types.py`. None were made. This means:
- The `scope` parameter (`quick` / `standard` / `full`) was never added to `AnalyzeRequest`
- The pipeline always runs all 8 steps regardless of deal type
- `chat.py` has no `thinking` or `artifact` SSE event types
- `NumericZoningParams` has no `source_refs` for per-claim citations
- The deal type selection is frontend-only decoration

### 2. Deal Type is Cosmetic, Not Functional
The `selectedDealType` state in `page.tsx` is used only to choose which hero card variant to render and whether to use `TabbedReport` or `ZoningReport`. It is never sent to the backend. The `streamAnalysis` function signature is:
```typescript
streamAnalysis(address, onStatus, onResult, onError)
```
No deal type parameter. The backend `AnalyzeRequest` schema is:
```python
class AnalyzeRequest(BaseModel):
    address: str
```
No deal type field. This means a "Wholesale" analysis runs the exact same zoning/density/proforma pipeline as a "Land Deal" analysis.

### 3. Wholesale, Creative Finance, and Hybrid Hero Cards Use Fabricated Metrics
- **Wholesale:** MAO is calculated as `ARV * 0.7` where "ARV" is actually `adv_per_unit` from the land pro forma — a completely different concept. Repair estimate is `ARV * 0.1` (a made-up percentage). Assignment fee is `min(ARV * 0.05, $15K)` (another approximation).
- **Creative Finance:** Missing Rate Spread and Monthly Cash Flow entirely. Shows Market Value and LTV as substitutes. Comments in code acknowledge these are "placeholder calculations."
- **Hybrid:** None of the planned metrics exist. Shows a generic mix of land and property data.

### 4. Agent Mode Redesign Was Completely Skipped
Phase 5 from the plan was not started. The `chat.py` file is unchanged. No thinking transparency, no artifact-first output, no pipeline plan approval, no enhanced tool use badges, no auto-tool-selection based on intent parsing.

### 5. No Tests Written
The plan specified Phase 6 as "Quality Testing — full quality gate." Zero tests were written:
- No component tests for `DealTypeSelector`, `DealHeroCard`, `TabbedReport`
- No Playwright tests for the new lookup flow with deal type selection
- No unit tests for the synthetic metric calculations
- No regression tests for the 4 bug fixes

### 6. ZoningReport Still Exists as a Parallel Component
`ZoningReport.tsx` was not refactored or replaced — `TabbedReport.tsx` was created alongside it. Both are imported in `page.tsx`. Agent mode still uses the old `ZoningReport` while lookup mode uses `TabbedReport`. This creates maintenance burden — any fix to the report display may need to be applied in two places.

---

## Section 7: What Needs Improvement

### 1. DealHeroCard Metric Accuracy
The wholesale and creative finance hero cards need real data pipelines, not client-side approximations. If the backend cannot provide wholesale-specific data (actual ARV from comps, repair estimates), the UI should show "Not available — this analysis type coming soon" rather than displaying fabricated numbers that could mislead users.

### 2. Tab Default Should Match Deal Type
Currently, `TabbedReport` defaults to the "property" tab. For a wholesale deal, the user likely wants to see the "deal" tab (comps) first. For creative finance, they need property data (existing mortgage info). The active tab should match the deal type's primary concern.

### 3. CapabilityChips Agent Mode Chips Are Static
The agent mode chips ("Analyze Property", "Generate Documents", "Search Comps", "Pro Forma") paste text into the input. They should either: (a) directly invoke the corresponding backend tool, or (b) at minimum send a structured tool request rather than a natural language prompt.

### 4. TabbedReport and ZoningReport Code Duplication
Both components render the same report data with similar sub-components (ParcelViewer, DensityBreakdown, FloorPlanViewer, BuildingRenderViewer, SetbackDiagram, PropertyIntelligence, DocumentGenerator). They should share a common foundation to prevent drift.

### 5. Error States in Hero Cards
When pipeline data is missing (no comps, no proforma), the hero cards show "N/A" everywhere. This is a poor user experience for wholesale/creative finance deals where most metrics will always be N/A because the data pipeline doesn't support them. The hero card should either hide unsupported metrics or show a clear "requires additional data" message.

---

## Section 8: Context Loss Analysis

The user noted that "when we compacted our specs we lost a lot of context because we implemented the claude code repo that optimizes our experience/productivity." Here is what was lost and its impact:

### What Was Lost

1. **Backend implementation details.** The research spec explicitly listed backend file changes: `schemas.py` (add scope), `routes.py` (conditional execution), `chat.py` (thinking/artifact events), `core/types.py` (source_refs). When context was compacted, these specific backend tasks likely fell out of the working memory, leaving only the frontend component names.

2. **The "scope" concept.** The research spec's Pattern 1 (Intent-Driven Pipeline Scoping) was the highest priority (P0) pattern. It called for `quick`/`standard`/`full` scope levels that would actually change which pipeline steps run. This entire concept was dropped — not deferred, but absent from the implementation.

3. **Agent mode phase details.** Phase 5 had four specific tasks: tool use badges, thinking transparency, artifact cards, and pipeline plan approval. Each had specific file changes and SSE event types defined. All four were skipped, suggesting the agent redesign phase was never reached or was dropped from the execution plan.

4. **Test requirements.** Phase 6 quality testing was detailed in the plan but no tests were written. This is likely because the execution focused on visible frontend deliverables and ran out of context/time before reaching testing.

5. **The distinction between "display" and "functional."** The plan was clear that deal types should change pipeline behavior, not just report presentation. This architectural distinction (backend-functional vs. frontend-cosmetic) was lost during context compaction, resulting in a frontend-only implementation.

### Impact

The implementation delivered a visually complete UX overhaul that looks like the spec but doesn't function like it. A user selecting "Wholesale" sees a wholesale-themed hero card, but the underlying analysis is identical to a land deal. This is a cosmetic layer over the same pipeline, not the deal-type-aware intelligence platform the spec envisioned.

The risk is that this creates a false impression of completeness. The design spec (written after implementation) marks patterns as "adopted" that are only partially implemented, which could cause future work to skip necessary backend changes.

---

## Section 9: Recommended Next Steps

Ranked by impact and dependency order:

### Priority 1: Backend Deal Type Support (High Impact, Blocking)
1. Add `deal_type: Literal["land_deal", "wholesale", "creative_finance", "hybrid"] = "land_deal"` and `scope: Literal["quick", "standard", "full"] = "standard"` to `AnalyzeRequest` in `schemas.py`
2. Pass `deal_type` from frontend `streamAnalysis` call
3. In `routes.py`, conditionally skip pipeline steps based on scope (quick skips comps/proforma, standard adds density calc, full runs everything)
4. Return deal-type-specific fields in the response

### Priority 2: Fix Synthetic Metrics (High Impact, Quick Win)
1. Replace fabricated wholesale/creative finance metrics with honest "Data not available" states or remove deal types that lack backend support
2. If keeping the deal types, add clear disclaimers: "Estimates based on available data. Actual ARV requires property inspection."
3. Alternatively, gate wholesale and creative finance as "Coming Soon" until real pipelines exist

### Priority 3: Write Tests (High Impact, Required for Merge)
1. Unit tests for `DealHeroCard` metric calculations (especially the synthetic ones)
2. Playwright test for the full lookup flow: enter address -> select deal type -> verify report tabs
3. Regression tests for the 4 bug fixes
4. Component render tests for `DealTypeSelector` and `TabbedReport`

### Priority 4: Unify ZoningReport and TabbedReport (Medium Impact)
1. Extract shared tab content into reusable components
2. Either migrate agent mode to use `TabbedReport` (with `dealType` optional), or create a shared base component
3. Delete redundant code in `ZoningReport.tsx` that is duplicated in `TabbedReport.tsx`

### Priority 5: Agent Mode Phase (Medium Impact, Requires Backend)
1. Add `thinking` SSE event type to `chat.py` — stream the agent's reasoning steps
2. Add `artifact` SSE event type for document generation
3. Create `ArtifactCard` component for styled download cards
4. Implement thinking transparency in the frontend (collapsible reasoning section)

### Priority 6: Per-Claim Citations (Lower Impact, High Effort)
1. Add `source_refs: dict[str, str]` to `NumericZoningParams` in `core/types.py`
2. During LLM extraction, map each extracted parameter to its source ordinance chunk
3. Render superscript citations in the Zoning tab dimensional standards table
4. This is the deepest change and has the most risk — defer until core deal type support is solid

---

## Section 10: Test Plan

### Manual Tests (Before Merge)

1. **Lookup flow, land deal:** Enter "7940 Plantation Blvd, Miramar, FL 33023" -> select "Land Deal" -> verify 8-step pipeline runs -> verify TabbedReport renders with hero card -> verify all 4 tabs have content -> verify "New Analysis" button works
2. **Lookup flow, wholesale:** Same address -> select "Wholesale" -> verify hero card shows wholesale metrics (ARV, MAO, etc.) -> verify same pipeline steps run (documenting that deal type doesn't change pipeline)
3. **Lookup rejects non-address:** Type "what is zoning" in lookup mode -> verify "I need a property address" message appears
4. **Agent mode chat:** Switch to agent mode -> type a question -> verify chat response streams -> verify tool use badges appear
5. **Agent mode address:** Enter an address in agent mode -> verify pipeline runs (not deal type selector)
6. **Autocomplete z-index:** Enter a partial address -> verify dropdown appears above capability chips
7. **Parcel boundary notice:** Analyze an address that returns no parcel geometry -> verify amber notice appears
8. **Mode toggle:** Switch between lookup and agent -> verify capability chips change -> verify input placeholder changes

### Automated Tests (Should Be Written)

```
tests/unit/test_deal_hero_card.ts
  - LandDealHero renders correct metrics from report data
  - LandDealHero handles null density_analysis gracefully
  - WholesaleHero computes MAO as 70% of ADV
  - CreativeFinanceHero shows N/A when market_value is 0
  - HybridHero displays correct metric labels

tests/unit/test_deal_type_selector.ts
  - Renders all 4 deal type cards
  - Calls onSelect with correct DealType when clicked
  - Buttons are disabled when disabled prop is true

tests/frontend/e2e/test_lookup_flow.spec.ts
  - Full lookup flow: address -> deal type -> pipeline -> report
  - Deal type selector appears after address entry
  - TabbedReport renders with correct tabs
  - Input bar hidden after report in lookup mode
  - New Analysis button resets state

tests/frontend/e2e/test_mode_routing.spec.ts
  - Lookup mode rejects non-address input
  - Agent mode allows free-form input
  - Mode toggle switches capability chips
  - Address in agent mode runs pipeline directly (no deal type selector)

tests/unit/test_bug_fixes.py
  - AI render endpoint uses async Gemini client
  - Parcel map shows notice when geometry is missing
```

---

## Appendix: Files Changed

### New Files
| File | Lines | Status |
|------|-------|--------|
| `frontend/src/components/DealTypeSelector.tsx` | 99 | New — deal type picker |
| `frontend/src/components/DealHeroCard.tsx` | 128 | New — strategy-specific metrics |
| `frontend/src/components/TabbedReport.tsx` | 494 | New — 4-tab report layout |
| `docs/superpowers/specs/2026-03-14-plotlot-ux-design.md` | 96 | New — design spec |
| `docs/superpowers/specs/2026-03-14-agent-ux-research.md` | 230 | New — research synthesis |

### Modified Files
| File | Key Changes |
|------|-------------|
| `frontend/src/app/page.tsx` | Deal type state, mode routing, TabbedReport integration, z-index fix |
| `frontend/src/components/AnalysisStream.tsx` | Narrative descriptions, step completion messages |
| `frontend/src/components/ArcGISParcelMap.tsx` | Missing geometry amber notice |
| `frontend/src/components/CapabilityChips.tsx` | Mode-specific chip sets |
| `src/plotlot/api/render.py` | Async Gemini client, model update to gemini-2.5-flash |

### Unchanged Files (Should Have Been Modified Per Spec)
| File | Planned Change | Status |
|------|---------------|--------|
| `src/plotlot/api/schemas.py` | Add `scope` and `deal_type` to `AnalyzeRequest` | Not done |
| `src/plotlot/api/routes.py` | Conditional pipeline step execution | Not done |
| `src/plotlot/api/chat.py` | `thinking` + `artifact` SSE events, intent parsing | Not done |
| `src/plotlot/core/types.py` | `source_refs` on `NumericZoningParams` | Not done |
| `frontend/src/lib/api.ts` | `scope` parameter on `streamAnalysis`, thinking/artifact handlers | Not done |
