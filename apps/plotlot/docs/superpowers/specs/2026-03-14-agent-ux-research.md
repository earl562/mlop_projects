# PlotLot Agent UX Research Synthesis

**Date:** 2026-03-14
**Status:** Specification
**Author:** Architecture Review
**Scope:** Comprehensive UX overhaul across Lookup and Agent modes

---

## 1. Executive Summary

PlotLot's current UX has three structural problems. First, the mode toggle between Lookup and Agent is cosmetic — both modes funnel into the same `sendMessage` function in `page.tsx`, which uses a regex heuristic (`extractAddress`) to decide between `runAnalysis` (full pipeline) and `streamChat` (agent). The `mode` state variable is never read during message routing. Second, the pipeline always runs all 8 steps (geocode, property, search, analysis, calculation, comps, proforma, result) regardless of what the user actually needs. A wholesaler who just wants to check zoning for a quick drive-by gets the same 30-second pipeline as someone building a full investment memo. Third, the report component (`ZoningReport.tsx`, 579 lines) renders every section unconditionally, creating cognitive overload for users who only needed one answer.

We researched four production AI applications — Z.ai, ChatGPT, Gemini, and MiniMax — to identify patterns that solve these exact problems. The findings converge on three principles: (1) let intent drive scope, not a global toggle; (2) show work transparently with collapsible reasoning; (3) structure output around the user's decision, not the pipeline's data model.

This spec defines 12 patterns to adopt, a new report output structure, refined mode definitions, and a phased implementation roadmap.

---

## 2. Comparison Table

| Dimension | Z.ai | ChatGPT | Gemini | MiniMax |
|-----------|-------|---------|--------|---------|
| **Tool Presentation** | Tool cards in Agent mode grid (AI Slides, Full-Stack, etc.) | Description-driven auto selection via `tool_choice: "auto"` | Gems as preset tool bundles | Capability-first navigation — pick output type first |
| **Intent Parsing** | Segmented toggle (Chat vs Agent) determines tool availability | Model weighs intent against tool descriptions autonomously | Deep Research shows plan for approval before executing | User selects capability category, then provides input |
| **Output Scoping** | Artifact-first — Agent produces files (.docx, .pdf), not prose | Canvas/split panel for long-form; chat stays left | Progressive disclosure via content parts (reasoning, result, citations separated) | 4-phase progress then final artifact in library |
| **Response Formatting** | Collapsed "Thought Process" after completion | Inline citations with character-position mapping; tool use badges | Per-claim grounding with startIndex/endIndex source mapping; table-first for comparative data | Generated content flows into persistent asset library |
| **Conversation Flow** | Toolbar changes per mode (web search + deep think vs upload only) | Conversations API with `previous_response_id` chaining | Thinking summaries as collapsible reasoning sections | Capability selection drives entire interaction frame |
| **Mode Switching** | Inline segmented control in input toolbar — frictionless | No explicit modes — model auto-routes based on context | Gems as shareable mode presets with custom instructions | Capability tabs at top level (Video, Music, Image, Voice) |
| **Loading / Progress** | Expandable "Thinking..." with real-time reasoning stream, "Skip" button | Streaming semantic events (`response.output_text.delta`, `response.completed`) | Research plan approval before execution; user can skip steps | 4-phase: "Optimizing prompt... Content compliance... Queuing... Generating..." |
| **Error Handling** | Progressive auth gates with value-explaining modals | Graceful degradation with retry | Grounding confidence scores per claim | Tiered access with visible-but-locked premium features |

---

## 3. Twelve Patterns to Adopt

### Pattern 1: Intent-Driven Pipeline Scoping (P0)
**Source:** ChatGPT, Gemini | **Phase:** Bug Fix
Instead of running all 8 steps, infer which are needed from the user's message. Add `scope` parameter (`quick`, `standard`, `full`) to `AnalyzeRequest`. Frontend infers scope from input content. Backend conditionally skips steps.
- `quick` = geocode + property + zoning search
- `standard` = + LLM analysis + density calculation
- `full` = + comps + proforma
**Files:** `api/schemas.py`, `routes.py`, `page.tsx`

### Pattern 2: Functional Mode Toggle (P0)
**Source:** Z.ai | **Phase:** Bug Fix
Mode toggle must actually control routing. Lookup: always `runAnalysis`, reject non-addresses. Agent: always `streamChat`, let agent decide tools. The `mode` state in `page.tsx` must be read during `sendMessage`.
**Files:** `page.tsx`

### Pattern 3: Narrative Pipeline Steps (P1)
**Source:** ChatGPT, Z.ai | **Phase:** Lookup Redesign
Replace bare step labels with contextual narrative: "Found property in Miramar, Broward County..." → "Searching RS5 zoning regulations..." → "Extracted 7 dimensional standards..."
**Files:** `routes.py`, `AnalysisStream.tsx`

### Pattern 4: Collapsible Report with Smart Defaults (P0)
**Source:** Gemini, Z.ai | **Phase:** Lookup Redesign
All sections collapse by default except Deal Summary Card. Different scopes show different default-open sections.
**Files:** `ZoningReport.tsx`

### Pattern 5: Tool Use Badges (P1)
**Source:** ChatGPT | **Phase:** Agent Redesign
Clickable "Used [Tool]" badges showing raw queries/results. Makes each tool activity expandable with args and truncated result.
**Files:** `page.tsx`, `chat.py`

### Pattern 6: Per-Claim Citations (P1)
**Source:** ChatGPT, Gemini | **Phase:** Quality
Each extracted zoning parameter links to its specific ordinance chunk via superscript citations. Add `source_refs` dict to `NumericZoningParams`.
**Files:** `ZoningReport.tsx`, `lookup.py`, `core/types.py`

### Pattern 7: Deal Summary Hero Card (P0)
**Source:** MiniMax, Z.ai | **Phase:** Lookup Redesign
Dense, scannable card at top of every report: Max Units, Est. Land Value, Max Offer Price, Governing Constraint, Confidence. Answers "Should I pursue this deal?" in 3 seconds.
**Files:** New `DealSummaryCard.tsx`

### Pattern 8: Thinking Transparency (P2)
**Source:** Z.ai, Gemini | **Phase:** Agent Redesign
Collapsible "Thinking..." section during agent reasoning. Streams real-time. Collapses to "Thought for 12s" after.
**Files:** `page.tsx`, `chat.py`

### Pattern 9: Scoped Report Output (P0)
**Source:** Gemini, ChatGPT | **Phase:** Lookup Redesign
Report only renders sections matching the pipeline scope. Quick scope: no comps/proforma/floor plan/render. Standard: adds density. Full: everything.
**Files:** `ZoningReport.tsx`, `api.ts`

### Pattern 10: Research Plan Approval (P2)
**Source:** Gemini Deep Research | **Phase:** Agent Redesign
"I'll analyze 123 Main St: geocode, property, zoning, density, comps, proforma. Skip any?" User can uncheck optional steps.
**Files:** New `PipelinePlanCard.tsx`

### Pattern 11: Artifact-First Agent Output (P1)
**Source:** Z.ai, ChatGPT | **Phase:** Agent Redesign
When agent generates a document, the primary output is a styled download card (ArtifactCard), not a chat message describing it. New `artifact` SSE event type.
**Files:** New `ArtifactCard.tsx`, `page.tsx`, `chat.py`

### Pattern 12: Table-First Comparative Data (P2)
**Source:** Gemini | **Phase:** Quality
Convert Dimensional Standards from key-value pairs to a structured table with columns: Parameter, Value, Source. Enables per-claim citations naturally.
**Files:** `ZoningReport.tsx`

---

## 4. Report Output Design Decision

### Recommendation: Deal Summary Card + Tabbed Sections

```
+-----------------------------------------------+
|  DEAL SUMMARY CARD (always visible)           |
|  ┌─────────┬─────────┬─────────┬────────────┐ |
|  │Max Units│Est Value│Max Offer│Confidence  │ |
|  │   12    │ $1.2M   │ $485K   │   HIGH     │ |
|  └─────────┴─────────┴─────────┴────────────┘ |
|  Governing: density_per_acre | RM-25 zoning   |
|  [Download PDF] [Generate LOI] [Save]          |
+-----------------------------------------------+
|                                                |
|  [ Property ][ Zoning ][ Analysis ][ Deal ]    |
|                                                |
|  (Selected tab content renders below)          |
+-----------------------------------------------+
```

| Tab | Content | Current Sections Mapped |
|-----|---------|------------------------|
| **Property** | Parcel viewer (split map + details), property intelligence flags | `ParcelViewer`, `PropertyIntelligence` |
| **Zoning** | District, dimensional standards table with citations, setback diagram, permitted uses | Zoning header, `DataRow`, `SetbackDiagram`, `UsesList` |
| **Analysis** | Density breakdown (4-constraint chart), floor plan, AI render | `DensityBreakdown`, `FloorPlanViewer`, `BuildingRenderViewer` |
| **Deal** | Comparable sales table, pro forma waterfall, document generator | Comps, pro forma, `DocumentGenerator` |

**Rationale:** A wholesaler evaluating 10 properties/day needs to scan the Deal Summary Card and move on. Tabs let them drill into specifics when a property passes initial screening. The current 579-line scroll forces them past floor plans and AI renders to find the max offer price.

---

## 5. PlotLot Mode Definitions

### Lookup Mode (Default)
**Contract:** Address in, report out. No conversation. No agent.
- User enters address (or selects from autocomplete)
- System runs pipeline with inferred scope
- Report renders with Deal Summary Card + tabbed sections
- Actions: "Analyze another address", "Download PDF", "Generate LOI", "Save"
- No chat, no follow-ups, no suggestion chips
- Non-address input → inline prompt: "Switch to Agent mode for questions"

**Scope inference:**
| Input | Scope | Steps |
|-------|-------|-------|
| Just an address | `standard` | geocode → property → search → analysis → calc |
| Address + "full analysis" | `full` | All 8 steps |
| Address + "just zoning" | `quick` | geocode → property → search |

### Agent Mode
**Contract:** Conversational. Agent auto-selects tools. Multi-turn.
- User types anything — address, question, command
- Agent decides tools via description-driven auto-selection
- Agent can run partial pipeline (just geocode + property for quick answer)
- Chat history persists (sidebar sessions)
- Tool use badges show what agent did
- Thinking transparency shows reasoning
- Artifact cards for generated documents

---

## 6. Implementation Roadmap

### Phase 3: Bug Fix

| Task | Pattern | Files | Priority |
|------|---------|-------|----------|
| Functional mode toggle | P2 | `page.tsx` | P0 |
| `scope` parameter to pipeline | P1 | `schemas.py`, `routes.py` | P0 |
| Frontend scope inference | P1 | `page.tsx` | P0 |
| Conditional step execution | P1 | `routes.py` | P0 |
| Scope-aware report rendering | P9 | `ZoningReport.tsx`, `api.ts` | P0 |
| Address autocomplete fix | Bug | `AddressAutocomplete.tsx`, `main.py` | P0 |
| Parcel boundary consistency | Bug | `ArcGISParcelMap.tsx`, providers | P0 |
| AI Render fix | Bug | `BuildingRenderViewer.tsx`, `render.py` | P0 |
| Lookup blocks chat | Bug | `page.tsx`, `InputBar.tsx` | P0 |

### Phase 4: Lookup Redesign

| Task | Pattern | Files |
|------|---------|-------|
| DealSummaryCard component | P7 | New: `DealSummaryCard.tsx` |
| Tabbed report layout | P4 | `ZoningReport.tsx` → extract 4 tab components |
| Narrative pipeline messages | P3 | `routes.py`, `AnalysisStream.tsx` |
| Smart section defaults | P4 | `ZoningReport.tsx` |

### Phase 5: Agent Redesign

| Task | Pattern | Files |
|------|---------|-------|
| Tool use badges | P5 | `page.tsx`, `chat.py` |
| Thinking transparency | P8 | `page.tsx`, `chat.py` |
| Artifact cards | P11 | New: `ArtifactCard.tsx`, `chat.py` |
| Pipeline plan approval | P10 | New: `PipelinePlanCard.tsx` |

### Phase 6: Quality

| Task | Pattern | Files |
|------|---------|-------|
| Per-claim citations | P6 | `ZoningReport.tsx`, `lookup.py`, `types.py` |
| Table-first standards | P12 | `ZoningReport.tsx` |
| Per-parameter confidence | P6 | `types.py`, `lookup.py` |

---

## 7. Key Architecture Changes

### Backend
1. `api/schemas.py` — Add `scope: Literal["quick", "standard", "full"] = "standard"` to `AnalyzeRequest`
2. `routes.py` — Conditional step execution based on `scope`
3. `chat.py` — Add `thinking` and `artifact` SSE event types. Include tool args/results in events.
4. `core/types.py` — Add `source_refs: dict[str, str]` to `NumericZoningParams`

### Frontend
1. `page.tsx` — Branch `sendMessage` on `mode`. Add scope inference.
2. `ZoningReport.tsx` — Refactor to tabbed layout. Extract `PropertyTab`, `ZoningTab`, `AnalysisTab`, `DealTab`.
3. `AnalysisStream.tsx` — Render narrative messages, not just step labels.
4. `api.ts` — Add `scope` to `streamAnalysis`. Add `thinking`/`artifact` SSE handlers.

### New Components
- `DealSummaryCard.tsx` — Hero card with key deal metrics
- `ArtifactCard.tsx` — Styled download card for generated documents
- `PipelinePlanCard.tsx` — Step selection before pipeline execution
- `PropertyTab.tsx`, `ZoningTab.tsx`, `AnalysisTab.tsx`, `DealTab.tsx` — Tab content

### Risk Mitigation
`ZoningReport.tsx` (579 lines) refactor: extract tab content into 4 new components first, then swap layout. Each change stays reviewable.
