# Chatbot UX Research: Gemini & MiniMax Patterns for PlotLot

Research date: 2026-03-14
Focus: Interaction patterns that scope output to user need, applicable to a real estate analysis tool.

---

## Part 1: Google Gemini UX Patterns

### 1.1 Structured Responses

Gemini uses several formatting strategies to scope output to what the user actually needs:

**Progressive disclosure through content parts.** Gemini responses are composed of distinct `parts` — text, executable code, code execution results, thought summaries, and inline images. Each part type renders differently. The frontend doesn't dump everything into a single markdown blob; it separates reasoning from results from citations.

**Table-first for comparisons.** When presenting comparative data (books, products, plans), Gemini defaults to tables with columns like author/year/description rather than prose paragraphs. This is critical for PlotLot: zoning parameters, comparable sales, and pro forma line items are inherently tabular.

**Welcome state persona routing.** Gemini Advanced offers multiple engagement personas at the welcome screen: "Helpful Productivity Partner," "Inspirational Creative Muse," "Transparent & Trustworthy Guide," "Insightful Synthesizer," and "Showcase of Possibilities." Each persona primes different response styles. The user self-selects their intent before the first message.

**Suggestion chips as intent declaration.** Rather than an open text box, Gemini presents contextual suggestions that tell the system what output format to expect before the user types anything. This front-loads intent classification.

**Key takeaway for PlotLot:** The current pipeline dumps all 8 steps into a single streaming report. Gemini's pattern suggests separating the "quick answer" (max units, governing constraint) from the full report, and letting the user drill into sections.

---

### 1.2 Deep Research

Deep Research is the most relevant Gemini pattern for PlotLot's multi-step pipeline. Here is how it works:

**Phase 1 — Research Plan (user approval gate).** When a user submits a complex query, Deep Research does NOT immediately start browsing. It first generates a multi-step research plan and presents it to the user for review. The user can modify the plan — add topics, remove sections, redirect focus — before execution begins. This prevents wasted compute on unwanted analysis.

**Phase 2 — Autonomous execution with streaming progress.** Once approved, the agent runs in the background (`background=true`). Progress is streamed via events:
- `interaction.start` — provides an interaction ID for reconnection
- `content.delta` — delivers incremental text and thought summaries
- `interaction.complete` — signals task completion

The system shows what it's currently doing: which queries it's running, which sources it's reading. If the connection drops, the user can reconnect using the interaction ID and resume from where they left off via `last_event_id`.

**Phase 3 — Structured report with inline citations.** The final output is a structured report whose format is steerable through the prompt. The documentation explicitly says developers can specify "sections and subsections, include data tables, or adjust tone" for different audiences (technical, executive, casual). Reports include inline citations linking text segments to source URLs.

**Phase 4 — Follow-up interactions.** After the report is delivered, users can ask follow-up questions using `previous_interaction_id`. This enables clarification, summarization of specific sections, or deeper dives — without restarting the entire research process.

**Estimated cost per task: $2–$5** depending on complexity, with the agent autonomously determining search depth.

**Key takeaway for PlotLot:** The research plan approval pattern is directly applicable. Before running the full 8-step pipeline (geocode through pro forma), PlotLot could show the user: "I'll analyze 123 Main St — here's what I'll do: (1) Locate property in Miami-Dade ArcGIS, (2) Search zoning code for RM-25 standards, (3) Calculate max units, (4) Find comparable sales within 3 miles, (5) Run a residual land pro forma. Proceed?" This lets the user skip steps they don't need (e.g., skip comps/proforma for a quick zoning check).

---

### 1.3 Gems (Custom Assistants)

Gems are Gemini's version of custom GPTs / specialized agents.

**Creation model.** Users define a Gem by providing:
- A name and description
- Custom instructions (system prompt equivalent)
- Personality/tone guidance
- Scope constraints (what it should and shouldn't do)

Pre-made Gems exist for common use cases, and users can create custom ones. Each Gem gets its own conversation thread, separate from the main Gemini chat.

**Scoping pattern.** The key UX insight is that Gems constrain the model's output space before the conversation starts. A "Writing Coach" Gem won't try to write code; a "Code Reviewer" Gem won't try to write poetry. The system prompt acts as a capability filter.

**Key takeaway for PlotLot:** PlotLot's mode toggle (Analysis vs. Chat) is a primitive version of this. Consider defining sharper modes: "Quick Zoning Check" (geocode + property + zoning only, no comps/proforma), "Full Deal Analysis" (all 8 steps), "Comp Search" (address + comparable sales only), "Investment Memo" (full pipeline + document generation). Each mode would set a different tool mask and output format.

---

### 1.4 Grounding and Citations

Gemini's grounding system is the most well-documented part of the API. Here's how it works:

**Automatic tool invocation.** When the `google_search` tool is enabled, the model autonomously decides whether to search. It generates search queries, processes results, and synthesizes a grounded response — all without explicit user instruction.

**Grounding metadata structure.** Every grounded response includes a `groundingMetadata` object containing:
- `webSearchQueries` — the actual search terms used (transparency into the model's reasoning)
- `searchEntryPoint` — rendered HTML/CSS for a search suggestion bar (required by ToS)
- `groundingChunks` — array of source objects with URIs and titles
- `groundingSupports` — text segment mappings linking specific response text (by `startIndex`/`endIndex`) to source indices

**Inline citation rendering.** The `groundingSupports` array maps specific text segments to their source indices. Developers use this to insert clickable inline citations at the exact positions where claims are made. This is fundamentally different from just listing sources at the bottom — it's per-claim attribution.

**Key takeaway for PlotLot:** PlotLot already has a `sources` array in ZoningReport. The upgrade would be per-claim citations — when the report says "max density 25 units/acre," that specific claim should link to the zoning ordinance section that states it. The `groundingSupports` pattern (startIndex/endIndex mapping text to source indices) is directly implementable. The current confidence badge (high/medium/low) could be augmented with per-parameter confidence tied to whether a grounding source was found.

---

### 1.5 Tool Use Presentation

Gemini presents multiple tool types with different UI treatments:

**Code execution.** Responses contain three part types in sequence: `text` (explanation), `executableCode` (the Python code), and `codeExecutionResult` (output). These render as distinct visual blocks, not interleaved prose. The user sees reasoning, code, and results as separate UI cards.

The code execution sandbox supports 40+ libraries (NumPy, Pandas, Matplotlib, etc.), has a 30-second timeout, and retries up to 5 times on failure. Generated Matplotlib charts appear as inline images. This is relevant for PlotLot's calculator — showing the calculation code alongside results would increase transparency.

**Image generation.** Gemini uses narrative prompting (descriptive paragraphs, not keyword lists). Images return as inline data with SynthID watermarks. Multi-turn editing allows iterative refinement: "make the lighting warmer" or "change the text to Spanish." Images are available at 512, 1K, 2K, and 4K resolutions.

**Video generation.** Uses a long-running operation pattern with polling. After submission, the API returns an operation object immediately, and the client polls at ~10-second intervals until `done: true`. Generated videos are MP4s stored server-side for 2 days. This async pattern is important for PlotLot's heavier pipeline steps (comps search can take 15+ seconds).

**Google Search.** Rendered with a required search suggestions bar (per ToS). The model decides autonomously whether to search, and which queries to run. Multiple searches within one request are counted separately for billing.

**URL Context.** Processes up to 20 URLs per request (34MB limit each). Content moderation runs on each URL. Retrieved content counts toward input tokens. Supports data extraction, document comparison, and content synthesis.

**Function calling orchestration.** Gemini supports two multi-tool patterns:
- Parallel: independent functions execute simultaneously (results mapped back via `tool_use_id`)
- Compositional: dependent functions chain sequentially (e.g., get location, then get weather for that location)

**Key takeaway for PlotLot:** PlotLot's pipeline is inherently compositional (geocode must finish before property lookup, which must finish before zoning search). But comps and proforma could run in parallel after the calculator completes. The AnalysisStream component should visually distinguish between "waiting for prerequisite" and "actively processing" states.

---

### 1.6 Canvas (Side Panel)

Gemini Canvas is a collaborative editing environment that separates generated content from the conversation thread.

**Design model.** Canvas opens as a side panel next to the chat. The conversation stays in the left column; the generated artifact (document, code, etc.) lives in the right panel. Users can:
- Edit the artifact directly in the panel
- Ask the chat to modify specific parts
- Export to Google Docs, Drive, and other Workspace apps

**Content types.** Canvas supports documents, code, and structured content. Code execution runs directly within the canvas environment.

**Separation of concerns.** The critical UX insight is that the conversation is about coordination ("make the introduction shorter," "add a section on setbacks") while the canvas holds the actual deliverable. This prevents the deliverable from being buried in a chat scroll.

**Cross-platform export.** Generated content can be pushed to Google Drive, Docs, Gmail, Calendar, Chat, Keep, and GitHub. This integrates the AI output into the user's existing workflow rather than trapping it in the chat interface.

**Key takeaway for PlotLot:** The ZoningReport component currently renders inline within the chat scroll. A canvas-style pattern would open the full report in a side panel (or overlay), keeping the chat available for follow-ups like "what if I combined these two parcels?" or "show me comps from the last 6 months only." The DocumentGenerator (LOI, PSA, pro forma XLSX) is a natural canvas artifact — it should live in an editable panel, not download immediately.

---

### 1.7 Thinking / Reasoning Display

Gemini exposes its reasoning process through thought summaries:

**Streaming thought summaries.** In streaming mode, the API delivers "rolling, incremental summaries" of the model's reasoning as it works. These are separate from the final answer — marked with a `thought: true` flag on the content part.

**Non-streaming mode.** Returns a single consolidated thought summary alongside the final response.

**Developer control.** Thought summaries are opt-in via `includeThoughts: true`. Developers can display them as collapsible "thinking" sections (like Claude's thinking blocks) or hide them entirely.

**Key takeaway for PlotLot:** During the AI Analysis step (when the LLM extracts NumericZoningParams from zoning ordinance chunks), showing thought summaries would dramatically increase trust. Instead of a spinner that says "Extracting standards...", the user could see: "Found section 33-284.1 — checking setback requirements... Front setback: 25ft confirmed in two sections... Density: 25 units/acre from Table 4.3..."

---

## Part 2: MiniMax / Hailuo AI UX Patterns

### 2.1 Platform Overview

MiniMax positions itself with the tagline "Minimize Effort, Maximize Intelligence" and "Intelligence with Everyone." Their product suite spans:

| Product | Purpose | Model |
|---------|---------|-------|
| MiniMax Agent | Intelligent assistant for work/life | M2.5 (text) |
| Hailuo Video | AI video generation | Hailuo 2.3 / 2.3 Fast |
| MiniMax Audio | Speech synthesis (40 languages, 5-sec voice cloning) | Speech 2.6 |
| Talkie | Character interaction | M2-Her |
| Music | Genre-specific music creation | Music 2.5+ |

The M2.5 model is described as having "stronger reasoning, broader knowledge, and more precise code generation." The M2-Her variant specializes in "Multi-Character Roleplay, Immersive Long-horizon Interaction."

### 2.2 Hailuo AI Interface Design

**Top-level navigation structure.** The interface uses a flat top nav with 5 primary sections: Home, Agent, Assets, Video, Image, Audio. This is a capability-first navigation pattern — users pick the output type first, then provide input.

**Agent as entry point.** The Agent section is positioned as the primary interaction mode, accessible at `agent.minimax.io`. It's separate from the creative tools (video, image, audio), suggesting that conversational interaction and media generation are distinct user journeys.

**Asset management.** Generated content flows into a persistent "Assets" library. This is a reusability pattern — users build a library of generated content rather than losing outputs in chat scroll. Each asset has metadata (generation parameters, model used, creation date).

**Input patterns.** The video generation interface uses a conversational prompt: "Describe the scene in your mind." It accepts text descriptions, image uploads for reference, and facial reference images. The interface supports multi-format uploads (images, videos, audio) via drag-and-drop.

### 2.3 Progress Indicators

Hailuo's video generation shows granular progress phases:

1. "Optimizing prompt..." — the system is enhancing the user's input
2. "Content compliance check..." — safety/moderation review
3. "Queuing..." — waiting for GPU resources
4. "Generating..." — active generation

This 4-phase progress model is more transparent than a single spinner. Each phase communicates what's actually happening, setting accurate expectations.

**Wait time differentiation.** Premium members see accelerated timelines; free-tier users see standard queue positions. This transparency about wait times (rather than hiding them) manages expectations effectively.

**Key takeaway for PlotLot:** PlotLot's AnalysisStream already shows 8 named steps, which is good. But each step currently just shows "complete" or "in progress." Hailuo's pattern suggests sub-step visibility: "Property Lookup" could expand to show "Querying Miami-Dade ArcGIS... Found parcel... Querying zoning overlay..." This granular feedback is especially valuable for the longer steps (AI Analysis can take 10-15 seconds).

### 2.4 Subscription-Gated Capabilities

Hailuo uses a tiered access model where capabilities unlock at higher subscription levels:

| Tier | Key Unlocks |
|------|-------------|
| Basic | 768P video, serial task execution |
| Standard | 1080P/10sec video, 2 parallel tasks |
| Master | Full 1080P, extended features |
| Premium | Unlimited Hailuo 01 model + 02 model access |
| Elite | Unlimited both models + full Agent access |

The UX pattern here is that higher tiers unlock both quality (resolution) and concurrency (parallel tasks). The interface shows these limitations transparently rather than hiding them behind error messages.

**Key takeaway for PlotLot:** If PlotLot ever introduces tiers, the pattern would be: free tier gets zoning lookup only, paid tier adds comps + proforma + document generation. The UI should show locked features as visible-but-disabled, not hidden.

### 2.5 Creative Output Formatting

**Carousel-based presentation.** The homepage uses a carousel with hero slides for different capabilities. Each slide has a prominent CTA ("Access API Now," "Try Agent Now") with layered visuals (background/middle/top image layers).

**Card-based feature highlighting.** Within carousel sections, capabilities are presented as vertical cards (three per section) with cover imagery and genre/category tags.

**Statistics-driven positioning.** The company overview uses numbered metrics prominently (user count, ratings, etc.) to build credibility.

**Music/audio case studies.** Music outputs display with cover imagery and genre tags (Metal, Meditative, R&B, Pop, Jazz, Blues), making browsing outputs feel like browsing a media library rather than reading chat history.

**Key takeaway for PlotLot:** PlotLot's report output is text-heavy. MiniMax's pattern of using cover imagery and category tags could apply to comparable sales: each comp could be a card with a satellite thumbnail, price, distance, and zoning tag — browsable like a property listing, not just a table row.

---

## Part 3: Patterns to Adopt for PlotLot

### 3.1 Research Plan Approval (from Deep Research)

**Current state:** User enters address, pipeline runs all 8 steps automatically.

**Proposed pattern:** After geocoding confirms the address, show a research plan card:

```
Analyzing: 123 NW 17th Ave, Miami Gardens, FL 33054
County: Miami-Dade | Zoning: RM-25 (Multi-family Residential)

Research plan:
[x] Property records (Miami-Dade ArcGIS)
[x] Zoning ordinance search (3,561 chunks indexed)
[x] Max unit calculation
[ ] Comparable sales (3-mile radius) — adds ~15s
[ ] Land pro forma — adds ~5s
[ ] Document generation (LOI, PSA)

[Run Selected] [Run All]
```

This lets a user who just wants zoning info skip the expensive comps/proforma steps. It also surfaces the data sources (which ArcGIS layer, how many zoning chunks are indexed) for transparency.

### 3.2 Inline Citations (from Grounding)

**Current state:** ZoningReport shows a sources list at the bottom and a single confidence badge.

**Proposed pattern:** Each extracted parameter should link to its source:

```
Max Density: 25 units/acre [Sec. 33-284.1 ¹]
Front Setback: 25 ft [Table 4.3 ²]
Max Height: 45 ft [Sec. 33-284.3 ³]
Max FAR: Not specified (assumed from density) [⚠ inferred]

Sources:
¹ Miami Gardens Code of Ordinances, Sec. 33-284.1 (Municode)
² Miami Gardens Code of Ordinances, Table 4.3 (Municode)
³ Miami Gardens Code of Ordinances, Sec. 33-284.3 (Municode)
```

Parameters without grounding sources get a warning indicator, immediately showing where the analysis is weakest.

### 3.3 Canvas/Side Panel for Reports (from Canvas)

**Current state:** ZoningReport renders inline in chat scroll. DocumentGenerator downloads files immediately.

**Proposed pattern:** When the pipeline completes, the report opens in a right-side panel. The chat column stays available for:
- "What if the lot was 15,000 sqft instead?"
- "Show me only comps from the last 12 months"
- "Generate an LOI for this property at $X"

The panel persists across follow-up messages. Documents (LOI, PSA, pro forma XLSX) render as editable previews in the panel before export.

### 3.4 Thought Summaries During Analysis (from Thinking)

**Current state:** AI Analysis step shows a spinner with "Extracting standards..."

**Proposed pattern:** Stream the LLM's reasoning as collapsible thought summaries:

```
AI Analysis ▼
  Reviewing 15 zoning ordinance sections...
  Section 33-284.1: Found "maximum density of 25 dwelling units per acre"
  Section 33-284.3: Found "maximum building height of 45 feet"
  Table 4.3: Found front/side/rear setback requirements
  Cross-referencing with RM-25 district standards...
  ✓ Extracted 8 of 10 parameters (2 not specified in code)
```

This builds trust by showing the model's work, especially when parameters are missing or uncertain.

### 3.5 Mode-Based Tool Masking (from Gems)

**Current state:** Two modes — Analysis and Chat — with chat having dynamic tool masking.

**Proposed pattern:** Define 4 sharper modes that each produce a different output format:

| Mode | Pipeline Steps | Output |
|------|---------------|--------|
| Quick Zoning Check | geocode + property + zoning + analysis | Zoning parameters only, no financials |
| Full Deal Analysis | All 8 steps | Complete ZoningReport with comps + proforma |
| Comp Search | geocode + property + comps | Comparable sales table with map |
| Investment Memo | All 8 + document gen | Full report + auto-generated LOI/PSA |

Each mode sets explicit tool masks and output format expectations upfront, so the system doesn't waste compute or screen space on unwanted sections.

### 3.6 Granular Progress Phases (from Hailuo)

**Current state:** 8 steps, each shows complete/in-progress binary state.

**Proposed pattern:** Key steps expand to show sub-progress:

```
Property Record ▼
  ├─ Querying Miami-Dade parcel layer... ✓
  ├─ Querying zoning overlay... ✓
  └─ Found: Folio 30-2104-000-0010, RM-25

AI Analysis ▼
  ├─ Searching 3,561 zoning chunks... ✓ (15 relevant found)
  ├─ Extracting numeric parameters... ⟳
  └─ 6 of 10 parameters found so far
```

This is especially valuable for the two slowest steps: AI Analysis (LLM extraction) and Comparable Sales (ArcGIS Hub queries across multiple layers).

### 3.7 Comp Cards as Browsable Gallery (from Hailuo/MiniMax)

**Current state:** Comparable sales shown as a table in ZoningReport.

**Proposed pattern:** Each comparable sale renders as a card with:
- Satellite/street view thumbnail (already have Google Maps API key)
- Sale price + price/acre + price/unit
- Distance badge
- Zoning code tag
- Sale date
- Lot size

Cards are horizontally scrollable on mobile, grid on desktop. Clicking a card zooms the parcel map to that comp's location. This makes comps feel like browsing property listings rather than reading a spreadsheet.

### 3.8 Async Operation Pattern for Heavy Steps (from Gemini Video Gen)

**Current state:** SSE stream blocks until all steps complete.

**Proposed pattern:** For steps that take >10 seconds (comps, proforma), use Gemini's long-running operation pattern:
1. Return the core zoning analysis immediately
2. Show "Comparable sales searching... (estimated 15-20s)" with a polling indicator
3. When comps complete, slide the results into the report without page reload
4. Same for proforma

This delivers the most-wanted answer (max units) in ~10 seconds while heavier analysis arrives asynchronously.

---

## Part 4: Anti-Patterns to Avoid

### 4.1 Dumping Everything at Once
Both Gemini and MiniMax scope output to what was asked. Gemini's Deep Research doesn't include financial analysis unless requested. PlotLot should not auto-run proforma for someone who just wants to know the zoning code.

### 4.2 Hiding Tool Activity
Gemini shows which search queries it ran, which URLs it read, which code it executed. PlotLot should show which ArcGIS layers were queried, which zoning sections were found, which LLM model was used (especially during fallback chain).

### 4.3 One-Shot Reports with No Follow-Up Path
Gemini's `previous_interaction_id` pattern enables follow-up research without restarting. PlotLot's chat mode supports this, but the analysis mode doesn't — once the report renders, there's no way to say "what if the lot was 20,000 sqft?" without starting over.

### 4.4 Source Lists Without Per-Claim Attribution
A list of sources at the bottom of a report doesn't tell the user which claim came from which source. Gemini's `groundingSupports` pattern (startIndex/endIndex to source index mapping) is the gold standard. PlotLot should link each extracted parameter to the specific zoning ordinance section it came from.

---

## Summary: Priority Implementation Order

| Priority | Pattern | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Thought summaries during AI analysis | Low | High trust improvement |
| 2 | Inline citations per parameter | Medium | High accuracy transparency |
| 3 | Research plan approval gate | Medium | Reduces unnecessary compute |
| 4 | Granular sub-step progress | Low | Better perceived performance |
| 5 | Canvas/side panel for reports | High | Enables follow-up workflows |
| 6 | Mode-based tool masking | Medium | Scopes output to need |
| 7 | Comp cards as browsable gallery | Medium | Better comp browsability |
| 8 | Async delivery of heavy steps | High | Faster time-to-first-answer |
