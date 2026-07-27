# PlotLot Direction B — Parcel Atlas / Evidence Dossier

Status: design contract complete; implementation is intentionally out of scope.

## Decision this direction optimizes

Before asking whether a site works, a developer must establish *which parcel it is*, which authority governs it, and which records actually support a conclusion. Direction B makes the parcel dossier—not a deal, workspace, pipeline, or chat—the stable unit of work.

> Can I prove this exact parcel, replay the records behind each conclusion, and see where feasibility must abstain?

## Direction signature

The recognizable idea is a **cadastral atlas folded into an evidence dossier**.

- Parcel/APN/folio is the primary locator and persistent identity, with a redacted address only as a secondary alias when available.
- The map is a working cadastral instrument: selection, geometry, labels, layers, and source age are visible, but it never becomes a generic explorer.
- The selected parcel opens as a dossier of source records; source order, authority, freshness, conflicts, and replays sit beside interpretation.
- Capacity, purchase ceiling, and LLM analysis are downstream sheets in that dossier. They cannot read as independent “insights.”
- A jurisdiction badge is an explicit truth claim, not a marketing flourish. Unsupported or conditional geography changes what the interface permits.

This is intentionally unlike a command center, a deal pipeline, a chat assistant, or a document vault.

## Primary user and job

**Primary user:** acquisition/preconstruction lead at a small residential builder-developer who needs to qualify a particular parcel before making or revising a land offer.

**Core job:** locate a parcel by APN/folio, inspect governing records, resolve zoning and overlays, understand the deterministic capacity case, set a provisional purchase ceiling, and hand off the exact missing evidence when the product must abstain.

**Secondary readers:** land-use counsel, civil/survey consultants, underwriting partner, entitlement manager, and investment-committee reviewer.

## Packet

| Artifact | Purpose |
| --- | --- |
| `DESIGN.md` | Interface signature, tokens, primitives, interaction, accessibility, and deliberate tradeoffs |
| `ROUTES_FLOW_PANEL_HIERARCHY.md` | Route map, task flow, panel/scroll ownership, keyboard order, and replay flow |
| `STATE_MATRIX.md` | Correct, uncertain, conflicted, unavailable, and abstaining behavior for every semantic domain |
| `RESPONSIVE_WIREFRAMES.md` | 1440×900, 768×1024, and 390×844 layout/specification plus content-stress rules |
| `CONTENT_FIXTURES_AND_GROUNDING.md` | Deterministic redacted fixture, coverage truth, record provenance, capacity, ceiling, and grounded LLM contract |
| `SELF_AUDIT.md` | Accessibility, overflow, focus, motion, truthful-market, and generated-reference audit |
| `reference-direction-b-v1.png` | Sole built-in ImageGen desktop visual reference; inspiration only |
| `imagegen.metadata.json` | Prompt binding, output file signature/dimensions/hash, and generated-text limitations |
| `fixture-direction-b-v1.json` | Redacted deterministic sample used by all written examples |
| `checksums.sha256` | Reproducibility manifest for the prompt, reference, fixture, and packet documents |
| `DONE_CLAIM.json` | Bounded completion claim and validation evidence |
| `../direction-b.prompt.md` | Versioned canonical ImageGen prompt |

## Non-goals

- A countywide, statewide, or nationwide availability claim
- A legal opinion, survey certification, entitlement guarantee, or appraisal
- Chat-first navigation or generic AI-assisted browsing
- CRM stages, portfolio KPIs, or a “deal command center” shell
- A lifestyle, beach, luxury, house, or aerial-hero real-estate aesthetic
- Concealing empty, stale, conflicted, or municipality-conditional records
- Converting a planned market into a disabled-but-optimistic analysis screen

## Principal tradeoffs

1. **Parcel continuity over cross-deal overview.** This makes source verification faster but leaves portfolio/pipeline management to a separate product surface.
2. **Record density over narrative simplicity.** Authority and freshness remain visible; progressive disclosure controls the reading load.
3. **Map as instrument, not spectacle.** It earns its space by confirming geometry and source context, not by displaying imagery.
4. **Conservative capacity and ceiling over an attractive headline.** Missing governing inputs produce a bounded range or abstention, not a maximal number.
5. **Structured grounded analysis over open-ended chat.** The LLM can summarize and identify gaps only from an enumerated record set; it cannot invent rules or substitute for professional review.

## Reference-image authority

The generated image is a visual reference for hierarchy, material, map/dossier/evidence proportion, and quiet cartographic palette. Its text and apparent numeric values are not factual product content. The written fixtures and state matrix override it, particularly for coverage, constraints, capacity, and the rule that unsupported claims must abstain.
