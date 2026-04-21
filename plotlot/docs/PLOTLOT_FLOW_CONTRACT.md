# PlotLot Flow Contract

## Product Intent

PlotLot should feel like a land feasibility system for acquisition-oriented builder-developers, not a generic chatbot with real-estate flavoring.

The product has two distinct flows and both should stay legible:

- `Lookup`: fast, address-driven feasibility
- `Agent`: persistent, higher-capability decision support

## Lookup Contract

Lookup is the quick-feasibility lane.

- Entry point: property address
- Primary question: what can this lot support under the current zoning context?
- First response should prioritize trust-critical facts over commentary
- The flow should stay structured and should not drift into open-ended chat behavior

### Required facts

- resolved parcel and jurisdiction context
- zoning district or governing zoning context
- setbacks and dimensional standards when available
- maximum allowable units
- governing constraint
- source references, confidence, and freshness cues

### Optional follow-on analysis

- comps
- pro forma
- document generation
- strategy suggestions

These can appear after the trust-critical feasibility answer, but should not delay that answer when the user only needs quick feasibility.

## Agent Contract

Agent is the deeper working lane.

- Entry point: follow-up questions, strategy questions, report refinement, and workflow tasks
- Purpose: help users continue work across sessions and across related property conversations
- Tone: intelligent real-estate assistant, not a generic assistant surface

### Intended durable behaviors

- session-persistent memory
- recall of prior conversations
- linked property and report context
- follow-up analysis without restarting from scratch
- capability expansion into documents, comps, and underwriting support

### Current boundary

The product direction is durable memory and recall. The current repo has agent UX, chat, and session-oriented client behavior, but the durable backend memory contract is still a planned capability rather than a completed one.

## Data Contract

PlotLot should clearly separate facts from analysis.

### Trust-critical facts

- parcel identity
- municipality and county context
- zoning designation
- setbacks and dimensional standards
- maximum allowable units
- governing constraint
- sources
- confidence
- freshness

### Optional downstream analysis

- comparable sales
- residual land value or pro forma outputs
- document generation
- strategy recommendations

Facts should be easy to verify. Optional analysis can be richer and more interpretive, but it should stay visibly downstream from the factual feasibility layer.

## UX Direction Without UI Redesign

The existing `Lookup` and `Agent` categories stay.

- `Lookup` becomes the fastest route to a feasibility answer
- `Agent` becomes the workspace for memory, recall, and broader assistance
- the user should always understand which lane they are in and what that lane is optimized for

## Delivery Implication

Future implementation work should avoid re-deciding these contracts.

- Do not turn `Lookup` into free-form chat
- Do not bury trust-critical facts under optional downstream analysis
- Do not market `Agent` as persistent unless the session and recall layer is actually durable
