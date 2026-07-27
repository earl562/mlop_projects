# PlotLot Direction A — Operational Intelligence Workbench

Status: design contract complete; implementation intentionally out of scope.

## Decision this direction optimizes

An acquisition or preconstruction lead needs one calm place to answer:

> What can this parcel support, what evidence supports that answer, what is the purchase ceiling, and what must be resolved before anyone relies on it?

The workbench keeps the parcel, capacity, underwriting, provenance, and next handoff in one continuous decision surface. Evidence always appears before interpretation. If a trust-critical fact is unavailable, conflicting, stale beyond policy, or outside enabled coverage, the system abstains and names the next evidence request.

## Direction signature

The recognizable idea is an **evidence ledger with an anchored decision rail**.

- The central evidence spine is the dominant surface.
- The acquisition decision remains visible while evidence is inspected.
- Coverage and jurisdiction are first-class evidence, not hidden configuration.
- A map is a supporting parcel artifact, never the home screen or primary navigation.
- Documents live in the same ordered evidence spine; there is no separate deal-room mode.
- LLM analysis is a small, structured, citation-bound brief; there is no generic chat canvas.
- Agent work appears as explicit handoffs with inputs, owner, blocker, and output contract.

This makes Direction A structurally distinct from a map-first explorer and from a document-centric deal room.

## Primary user and job

**Primary user:** a small-to-mid-sized residential builder-developer, acquisition manager, or preconstruction lead screening a real parcel under time pressure.

**Common job:** resolve parcel and jurisdiction, verify zoning and dimensional constraints, compute a supportable maximum-unit case, compare the land basis, establish a purchase ceiling, and route unresolved evidence to the right agent or person.

**Secondary readers:** underwriting partner, civil engineer, land-use counsel, surveyor, investment committee reviewer.

## Artifacts

| Artifact | Purpose |
|---|---|
| `DESIGN.md` | Atmosphere, tokens, typography, primitives, interaction, motion, and accessibility contract |
| `ROUTES_FLOW_PANEL_HIERARCHY.md` | Route map, primary task flow, panel hierarchy, keyboard order, and scroll ownership |
| `STATE_MATRIX.md` | Full semantic state vocabulary and per-domain correct-or-abstain behavior |
| `RESPONSIVE_WIREFRAMES.md` | 1440×900, 768×1024, and 390×844 wireframes plus overflow/content-stress behavior |
| `CONTENT_FIXTURES_AND_GROUNDING.md` | Redacted South Florida fixtures, coverage truth, evidence provenance, documents, grounded LLM, and handoff schemas |
| `SELF_AUDIT.md` | Accessibility, hierarchy, overflow, heading-wrap, focus, reduced-motion, and market-specificity audit |
| `reference-direction-a-v4.png` | Selected truth-table-correct, opaque-identifier desktop visual reference from the single fresh built-in ImageGen call for this correction |
| `reference-direction-a-v3.png` | Historical rejected reference; generated queue copy included address-like text |
| `reference-direction-a-v2.png` | Historical rejected reference; its rail showed current figures while parking was not hash-bound |
| `reference-direction-a-v1.png` | Preserved historical visual reference; not selected |
| `imagegen.metadata.json` | Built-in tool-call/output binding, invocation timestamp, prompt hash, image hash, dimensions, and known limitations |
| `design-truth-contract.json` | Versioned machine-consumed state, dependency, coverage, and privacy contract |
| `design-truth-contract.sha256` | Canonical truth-contract hash binding |
| `checksums.sha256` | Final package hashes |
| `DONE_CLAIM.json` | Bounded design-only completion claim |
| `../direction-a.prompt.md` | Versioned canonical ImageGen prompt |
| `fixtures/redacted-acquisition-case.json` | Deterministic redacted illustrative fixture backing the content contract |

## Content-block jobs

| Block | Job |
|---|---|
| Deal queue | Navigate retained parcel decisions without changing product modes |
| Parcel identity | Prove the subject parcel before any zoning claim |
| Jurisdiction and coverage | Establish governing lane and whether analysis is allowed |
| Zoning | Show designation, authority, freshness, and cited excerpt |
| Dimensional rules | Expose setbacks, height, coverage, FAR, parking, and missing rules |
| Overlays and constraints | Surface flood, environmental, historic, utilities, access, and other governing overlays |
| Capacity | Show deterministic maximum units, formulas, inputs, and governing constraint |
| Survey / plat / construction documents | Tie uploaded and sourced artifacts into the same evidence chain |
| Comps | Explain comparable inclusion/exclusion and adjustment basis |
| Underwriting | Show assumptions and purchase ceiling downstream from capacity |
| Provenance | Bind every material fact and derived output to immutable evidence identifiers and hashes |
| Opportunity brief | Summarize only claims supported by cited evidence |
| Blocker | State the exact reason to abstain and the next acceptable evidence |
| Agent handoff | Assign a bounded task with known inputs and an auditable expected output |

## Non-goals

- Nationwide or countywide availability claims
- A legal opinion or entitlement guarantee
- A chat-first assistant
- A satellite or parcel map as the organizing surface
- A folder tree or file browser as the product’s central metaphor
- Lifestyle, luxury, beach, resort, or palm-tree branding
- Synthetic testimonials, fake partner marks, or vanity KPIs
- Decorative AI motion, AI glow, or undifferentiated purple/blue gradients

## Principal tradeoffs

1. **Evidence density over visual spectacle.** The surface is intentionally information-dense, but grouping, shared baselines, and progressive row disclosure keep it calm.
2. **One decision canvas over specialized modes.** Advanced map inspection and document editing may still use focused secondary routes, but they return to the same deal and never replace the workbench as the source of truth.
3. **Explicit unavailable states over optimistic continuity.** Planned or unsupported markets remain useful for APN/jurisdiction capture and waitlisting, but analysis controls stay disabled.
4. **Sequential mobile reading over desktop parity.** Mobile preserves the decision sequence and evidence fidelity, not the three-panel geometry.
5. **Structured LLM output over conversational flexibility.** This reduces open-ended interaction but makes claims inspectable, correctable, and safe to abstain.

## Reference-image authority

The selected `reference-direction-a-v4.png` is bound to the single fresh built-in `image_gen.imagegen` call for the opaque-identifier privacy correction and to canonical prompt `direction-a/v1.2.0` through `imagegen.metadata.json`. Its rail visibly abstains from maximum units and purchase ceiling because parking is not hash-bound, and every visible deal/parcel identifier is an opaque synthetic `DEAL-*` ID. `design-truth-contract.json` is the machine-consumed semantic contract; the prompt is hash-bound generation input, not executable contract prose. The raster is a visual reference for density, hierarchy, panel proportion, hairline material, abstained-state treatment, and opaque identifier treatment. It is not implementation code or a production data source.
