# ChatGPT Agent & Tool UX Patterns -- Research Report

**Date:** 2026-03-14
**Purpose:** Inform PlotLot's real estate analysis tool UX with concrete patterns from OpenAI's ChatGPT ecosystem.

---

## 1. Auto Tool Selection

### How ChatGPT Decides Which Tools to Use

ChatGPT uses **fully autonomous tool selection** by default. The model inspects the user's message, evaluates available tools against the request, and decides whether to invoke zero, one, or multiple tools -- all without user intervention.

**Key mechanism: `tool_choice` parameter**
- `"auto"` (default): Model freely decides; may call zero or many tools
- `"required"`: Must call at least one tool
- `"none"`: Prevents all tool calls
- `{"type": "function", "function": {"name": "..."}}`: Forces a specific tool
- `"allowed_tools"`: Restricts to a named subset

**Decision factors the model weighs:**
1. Whether the user's request maps to any available tool description
2. Whether required parameters can be inferred from conversation context
3. Ambiguity -- if inputs are unclear, the model asks for clarification rather than guessing
4. The quality of tool descriptions and parameter documentation (better descriptions = better selection)

**Parallel tool calls:** GPT-4o and later can invoke multiple tools simultaneously in a single turn. For example, if a user asks about weather in two cities, the model fires off both weather API calls at once. This can be disabled with `parallel_tool_calls: false`.

**Dynamic tool loading (GPT-5.4+):** A `tool_search` feature dynamically loads relevant tools into context to optimize token usage, rather than passing all tool definitions every turn.

### PlotLot Implications
- PlotLot already uses dynamic tool masking (unlocking tools based on conversation state). This aligns well with ChatGPT's approach but could go further by using rich tool descriptions to let the LLM auto-select more naturally.
- Consider moving from hard-coded masking to description-driven selection with guardrails.
- Parallel tool calls could speed up the pipeline: fire geocode + web search simultaneously when an address is provided.

---

## 2. Structured Output

### How ChatGPT Formats Structured Responses

OpenAI provides **Structured Outputs** -- a system that guarantees API responses conform to a JSON schema.

**Implementation:**
- Developer supplies a JSON Schema via `response_format: {type: "json_schema", json_schema: {...}}`
- The model's output is constrained to match the schema exactly
- No need for retry logic on malformed responses
- Works with Pydantic (Python) and Zod (JavaScript) for native schema definition

**Key design patterns:**
- **Chain of thought**: Structured step-by-step reasoning within defined schema fields
- **Data extraction**: Converting unstructured text into typed fields (e.g., extracting property data from zoning ordinances)
- **UI generation**: Formatting responses specifically for interface rendering -- the model outputs data in a shape ready for card/table/chart components

**Strict mode for tool calls:** Setting `strict: true` on tool definitions guarantees tool call arguments match the schema exactly, eliminating type mismatches in production.

### PlotLot Implications
- PlotLot's `NumericZoningParams` extraction already follows this pattern via tool calling with Pydantic models.
- Could extend structured outputs to format the entire `ZoningReport` response for direct frontend rendering without parsing.
- Consider defining JSON schemas for each UI card type (property card, density breakdown, comp analysis) so the LLM outputs render-ready data.

---

## 3. Canvas / Artifacts

### How ChatGPT's Canvas Works

Canvas is a **side panel workspace** that opens alongside the main chat conversation. It separates long-form content from the conversational flow.

**When canvas activates:**
- When the model generates substantial code, documents, or structured content
- When iterative editing is more useful than sequential chat messages
- The model decides autonomously when canvas is appropriate (not user-triggered)

**Key design principles:**
- **Split-view layout**: Chat on the left, canvas on the right
- **Content isolation**: Long documents/code don't clutter the conversation thread
- **Inline editing**: Users can directly edit content within canvas
- **Iterative refinement**: Multi-turn edits happen in-place rather than regenerating entire documents
- **Mode-specific features**: Code mode has different tools (run, debug, explain) than writing mode (shorten, expand, adjust tone)

**What goes to canvas vs. inline:**
- Canvas: Full documents, complete code files, article outlines, long-form analysis
- Inline: Short answers, conversational responses, quick code snippets, data summaries

### PlotLot Implications
- PlotLot's ZoningReport already functions somewhat like a canvas artifact -- it's a structured output that appears as a card alongside chat
- Could adopt the split-panel pattern: chat on the left, full zoning report / pro forma / document generator on the right
- Document generation (LOI, PSA) is a natural canvas use case -- show the generated document in a side panel where the user can request edits
- The key insight: **don't force long content into the chat stream**. Give it dedicated real estate.

---

## 4. Response Formatting

### How Different Content Types Are Presented

**Text responses:**
- Markdown rendering with headers, bold, lists, tables
- Inline citations with clickable links (especially for web search results)
- Progressive disclosure -- key findings first, details expandable

**Code:**
- Syntax-highlighted code blocks with language labels
- Copy button on code blocks
- In canvas: full editor with run/debug capabilities
- Code Interpreter outputs shown as separate result blocks

**Data & tables:**
- Markdown tables for structured comparisons
- Code Interpreter generates charts/visualizations as downloadable images (PNG, JPEG, GIF)
- File outputs (CSV, Excel) provided as downloadable links

**Images:**
- Generated images rendered inline in the conversation
- Progressive rendering: 1-3 partial renders during generation for faster perceived performance
- Multi-turn editing: "now make it more realistic" references the previous generation

**Citations (web search):**
- Inline citations as superscript numbers
- Each citation includes: URL, title, source location, character position indices
- Must be "clearly visible and clickable" per OpenAI's guidelines
- A `sources` field lists all URLs consulted (often more than inline citations)

**File search results:**
- Citations include file ID, filename, and character indices
- Allows tracing which source documents informed the answer

### PlotLot Implications
- PlotLot should adopt inline citations for zoning ordinance sources -- show which specific chunks informed the analysis
- Progressive image rendering could apply to satellite map / parcel map loading
- Data tables for comp analysis should be rendered as structured Markdown or as dedicated card components
- Pro forma results should have downloadable file links (XLSX export)

---

## 5. Conversation Flow -- Multi-Turn Patterns

### How Context Carries Across Messages

**Manual state management:**
- Full conversation history (alternating user/assistant messages) passed with each API request
- Developer responsible for managing and truncating history

**Automatic state management (Conversations API):**
- Conversations are durable objects with their own IDs
- Persist across sessions, devices, and jobs
- Use `previous_response_id` to chain responses without manually passing history
- 30-day retention by default; configurable

**Context window management:**
- Token limits encompass both input and output
- Content exceeding the window may be truncated
- Developers must monitor cumulative token usage across turns

**Prompt caching:**
- Static content (system instructions, tool definitions) cached automatically
- Reduces latency by up to 80% and input token costs by up to 90%
- Requires at least 1024 tokens; caches last 5-60 minutes in memory, up to 24h on newer models
- Best practice: put repetitive content (system prompt, examples) at the beginning of messages

**Memory system:**
- Automatic memory: conversation summaries injected at chat start
- Project-scoped memory: isolated context per project, preventing cross-contamination

### PlotLot Implications
- PlotLot's LRU session cache (100 sessions, 1hr TTL) aligns with ChatGPT's conversation persistence model
- Consider implementing project-scoped memory -- if a user analyzes multiple properties, maintain a "deal pipeline" context
- The geocode cache (session-level lat/lng) is already a good pattern; extend to cache property records and zoning data per session
- Token budget (50K per session) should be monitored and displayed to users approaching limits

---

## 6. Tool Use Indicators

### How ChatGPT Shows What Tools It's Using

**Clickable disclosure:**
- A "Used [Tool Name]" badge appears in the response (e.g., "Used Wolfram")
- Clicking reveals the exact query sent to the tool and the raw results received
- Provides transparency and lets users verify the model didn't fabricate data

**Web search indicators:**
- Search queries are logged as "search actions" in the response metadata
- Users can see what was searched, which pages were opened, and which in-page searches were run
- Inline citations link directly to source material

**Code Interpreter indicators:**
- Code execution shown in a distinct block -- the user sees the Python code that was written
- Output (text, charts, files) displayed separately from the code
- Iterative: if code fails, the model rewrites and re-runs, showing each attempt

**File search indicators:**
- `file_search_call` output shows the search ID and queries used
- Results include specific document citations with file IDs

**Agent mode progress:**
- Multi-step tasks show each step as it executes
- The model narrates what it's doing ("Searching for...", "Analyzing...", "Generating...")
- Each tool invocation produces a visible output item in the response stream

### PlotLot Implications
- PlotLot's SSE pipeline steps (geocode, property, zoning, analysis, calculator) already provide progressive disclosure
- Could enhance with clickable "Used ArcGIS" or "Used Zoning Search" badges that expand to show raw queries and results
- Show the actual zoning ordinance chunks that were retrieved, not just the extracted parameters
- Add transparency for LLM extraction: show which model was used (NVIDIA NIM vs. fallback) and the raw tool call

---

## 7. GPT Store / Custom GPTs

### How Custom GPTs Define Their Tool Sets

**Configuration components:**
1. **Custom instructions**: Natural language description of the GPT's behavior, personality, and constraints
2. **Knowledge files**: Uploaded documents the GPT can search via file search
3. **Actions**: External API integrations defined via OpenAPI schemas
4. **Conversation starters**: Pre-defined prompts to guide users
5. **Built-in tool toggles**: Enable/disable web search, code interpreter, image generation

**Action definition (OpenAPI):**
- Developers provide a standard OpenAPI schema describing available API endpoints
- The `info.description` field is critical -- ChatGPT uses it to determine when the action is relevant
- Endpoint names and parameter descriptions guide the model's auto-selection
- Authentication (API key or OAuth) is configured once and handled transparently

**Model's decision process for actions:**
1. Evaluate user query against action descriptions to determine relevance
2. Select the appropriate endpoint
3. Generate JSON parameters matching the schema
4. Execute the API call with configured authentication
5. Present results in natural language

**Key design insight:** The user never sees the OpenAPI schema or technical details. They "simply ask a question in natural language, and ChatGPT provides the output in natural language as well."

### PlotLot Implications
- PlotLot could expose its pipeline as a Custom GPT action: define an OpenAPI schema for `/analyze` and `/chat` endpoints
- Alternatively, the internal architecture already mirrors this pattern -- the LLM chat agent has tool definitions that function like GPT actions
- The emphasis on clear tool descriptions driving auto-selection validates PlotLot's approach of detailed tool schemas in `chat.py`
- Conversation starters map directly to PlotLot's suggestion chips ("Analyze 1234 Main St, Miami" etc.)

---

## 8. Loading / Streaming

### How Processing State Is Shown

**Token streaming (SSE):**
- Text arrives as `response.output_text.delta` events, rendered character-by-character
- Semantic event types: `response.created`, `response.output_text.delta`, `response.completed`, `error`
- Tool-specific events for code interpreter, file search, and image generation
- Each event is typed, allowing the UI to handle only relevant categories

**Tool use progress:**
- Tool calls appear as distinct "items" in the response stream
- A `function_call` item appears first (showing what's being called), followed by `function_call_output` (showing the result)
- For image generation: 1-3 progressive partial renders during generation
- Code Interpreter: shows code being written, then execution output separately

**Agent mode (multi-step):**
- Each step produces visible output items
- The model narrates its actions between tool calls
- Long-running tasks show intermediate state (e.g., "Searching for comparable sales...")
- The conversation is a stream of interleaved model text and tool call/result pairs

**Streaming best practice:**
- Content moderation is harder on partial completions
- UIs should handle incomplete state gracefully
- Use `response.completed` to finalize rendering

### PlotLot Implications
- PlotLot's SSE pipeline with typed events (geocode, property, zoning, analysis, calculator, heartbeat, done, error) closely mirrors ChatGPT's streaming model
- Could add partial rendering: show the property record card as soon as it arrives, don't wait for the full pipeline
- Heartbeat events (every 15s for Render's proxy) are already implemented -- this is the right pattern
- Consider adding narrative text between pipeline steps ("Found property in Miami-Dade County...", "Searching zoning ordinance for RM-25...")

---

## 9. ChatKit -- Pre-Built Chat UI Components

OpenAI's ChatKit is their embeddable chat solution for agentic applications. It provides:

- **Embeddable chat widgets** for frontend integration
- **File attachment support** for document handling
- **Chain-of-thought visualizations** showing agent reasoning
- **Card-based response formats** for structured data
- **Tool invocation display** showing when and how tools are called
- **Streaming response rendering**
- **Custom theming system** for brand alignment
- **Two deployment models**: OpenAI-hosted or self-hosted

### PlotLot Implications
- PlotLot's frontend components (AnalysisStream, ZoningReport, ParcelViewer) serve a similar purpose to ChatKit widgets
- The "card-based response format" pattern validates PlotLot's approach of rendering pipeline results as distinct cards
- Chain-of-thought visualization could be added to show the LLM's reasoning when extracting zoning parameters
- Custom theming aligns with PlotLot's dark mode / design system tokens

---

## 10. Concrete UI Patterns for PlotLot Adoption

### High Priority

1. **Tool Use Badges with Expandable Details**
   - Show "Used ArcGIS Property Lookup" badge on property data
   - Show "Used Zoning Ordinance Search" badge on zoning results
   - Click to expand: show raw ArcGIS query URL, returned fields, confidence
   - This builds trust in a real estate analysis context where data provenance matters

2. **Inline Source Citations**
   - Superscript numbers linking to specific zoning ordinance chunks
   - "Sources consulted" section at bottom of analysis
   - Each citation: section number, chapter title, municipality, chunk preview
   - Critical for RE professionals who need to verify regulations

3. **Split-Panel Canvas for Documents**
   - Chat on left, generated document (LOI, PSA, pro forma) on right
   - User can request edits in chat; document updates in-place
   - Download button always visible on document panel
   - Tabbed panels for switching between report, document, map

4. **Progressive Pipeline Rendering**
   - Render each card as its data arrives (don't wait for full pipeline)
   - Narrative text between steps: "Found property at 1234 Main St..." -> "Searching zoning code RM-25..." -> "Calculating maximum density..."
   - Skeleton loaders for cards not yet populated
   - Estimated time remaining based on pipeline step

### Medium Priority

5. **Parallel Tool Execution Display**
   - When geocode and web search run simultaneously, show both spinners
   - Branching progress indicator (like a mini pipeline graph)
   - Converge when both complete, then show unified result

6. **Structured Output Cards**
   - Property card: key metrics in a grid (lot size, zoning, assessed value)
   - Density card: 4-constraint visual breakdown (already exists)
   - Comp card: sortable table with price/acre, distance, sale date
   - Pro forma card: waterfall chart (GDV -> costs -> margin -> max land price)

7. **Conversation Memory Indicators**
   - Show what the system remembers: "Current property: 1234 Main St, Miami-Dade"
   - Display session context (like ChatGPT's project memory)
   - Token budget usage indicator (50K budget, X% used)

8. **Model Transparency**
   - Small badge showing which model handled extraction: "Claude Sonnet 4.6" or "NVIDIA NIM Llama 3.3"
   - Confidence indicator on extracted parameters
   - Flag when fallback model was used

### Lower Priority

9. **Smart Suggestion Chips**
   - Context-aware follow-up suggestions after analysis completes
   - "Generate LOI" / "Run Comp Analysis" / "Show Pro Forma" / "Expand Setback Details"
   - Mirrors ChatGPT's conversation starters but dynamically generated

10. **File Export as First-Class Output**
    - Pro forma XLSX as inline download card (not buried in a menu)
    - PDF report generation with progress indicator
    - Multiple export formats shown as a card with format options

---

## Summary of Key Takeaways

| ChatGPT Pattern | PlotLot Current State | Recommended Action |
|---|---|---|
| Auto tool selection via descriptions | Hard-coded tool masking by state | Hybrid: keep guardrails but enrich tool descriptions |
| Structured outputs with JSON schema | Pydantic models for extraction | Extend to full report rendering schema |
| Canvas side panel for long content | Reports rendered inline in chat | Add split-panel for documents & reports |
| Inline citations with sources | Sources listed but not inline | Add superscript citations to zoning analysis |
| Tool use badges (expandable) | Pipeline steps shown progressively | Add clickable badges with raw query/result details |
| Parallel tool calls | Sequential pipeline | Parallelize independent steps (geocode + web search) |
| Streaming with semantic events | SSE with typed events | Add narrative text between pipeline steps |
| ChatKit card components | Custom React components | Formalize card system as reusable design system |
| Conversation state persistence | LRU cache, 1hr TTL | Add project-scoped memory for deal pipelines |
| Model routing transparency | Fallback chain (silent) | Show which model handled each step |
