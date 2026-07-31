# PlotLot production design selection

Status: accepted design contract; frontend implementation is intentionally deferred.

## Decision

Select **Direction A — Operational Intelligence Workbench**.

Direction A wins the deterministic rubric at **100.0/100** with no blocking defect. Direction C scores **83.2/100** and remains a useful source for explicit ownership and review handoffs. Direction B scores **72.8/100** and remains a useful source for focused parcel geometry inspection. Neither secondary direction replaces the selected workbench grammar.

## Why the directions are genuinely different

The alternatives differ at the level of the product’s home object, not merely palette or styling.

Direction A makes the home object a continuous evidence ledger feeding an anchored acquisition decision. Its fastest path is parcel identity → jurisdiction/coverage → rules → constraints → capacity → underwriting → blocker/handoff. This minimizes mode changes for the common acquisition and preconstruction decision.

Direction B makes the home object a selected parcel on a cadastral atlas with an adjacent record dossier and evidence replay spine. It is strongest when geometry and source-record exploration dominate, but its map allocation slows the repeated evidence-to-decision loop and becomes less resilient when compressed.

Direction C makes the home object a stage-gate binder passed between accountable roles. It is strongest for formal handoff and sign-off, but users must traverse gate structure to reconstruct the complete current decision. That makes it better as a workflow pattern inside the selected system than as PlotLot’s primary information architecture.

## Criterion comparison

**Workflow speed.** Direction A keeps evidence, governing constraint, purchase ceiling, blocker, and next handoff in one continuous surface. Direction C adds review clarity but also gate navigation. Direction B gives the map the most space even when the user’s immediate job is evidence synthesis.

**Evidence comprehension.** Direction A’s numbered ledger creates a stable reading sequence and keeps source, citation, freshness, and hash adjacent to every fact. Direction C is also replayable, but evidence is partitioned by gate. Direction B makes source replay strong while splitting attention among map, dossier, and evidence rail.

**Market specificity.** All three packets correctly bind Miami-Dade to private beta, require municipality resolution for Broward and Palm Beach, and keep San Diego planned/not enabled. Direction A exposes these states in the retained queue and the evidence sequence, so geography changes both copy and permitted actions at the earliest useful point.

**Accessibility.** Direction A specifies DOM order, focus-visible treatment, non-color status, reduced motion, 44px touch targets, 200% zoom, 320px reflow, and one mobile scroll owner. Direction B’s map interaction and three simultaneous regions carry more keyboard and reflow risk. Direction C’s gate list is accessible but adds navigation before evidence.

**Responsive integrity.** Direction A intentionally changes composition: three regions at desktop, evidence plus rail at tablet, and one sequential column plus a decision dock on mobile. Direction C also stacks coherently. Direction B’s map-first identity loses more of its core proposition when the atlas collapses.

**Brand continuity.** Direction A preserves PlotLot’s Geist families, warm light surfaces, green evidence confidence, restrained amber/ochre intervention, and land-analysis identity while removing the current generic chat/SaaS shell. It evolves the product rather than introducing an unrelated cartographic or approval-product brand.

## Binding artifacts

- Deterministic scores: `scoring.json`
- Packet/provenance audit: `packet-audit.json`
- Required route, state, and viewport coverage: `acceptance-matrix.json`
- Current-app baseline findings and Todo21 resolution criteria: `iteration-ledger.json`
- Authoritative implementation contract: `../../../DESIGN.md`
- Architecture decision: `../../../docs/adr/0019-select-operational-intelligence-workbench.md`

## Reference authority and raster ban

The three PNG files are composition references only. They may inform hierarchy, density, material, and responsive intent. They must never be shipped as a page background, image map, canvas substitute, hit target, OCR content source, or screenshot embedded beneath interactive controls. Product facts, accessible names, focus order, layout, and states must be implemented with semantic DOM and shared design-system primitives. Written specifications override raster text and generated dimensions.

Direction A's selected reference is `../direction-a/reference-direction-a-v4.png`. It is bound to canonical prompt `direction-a/v1.2.0` and exactly one fresh built-in `image_gen.imagegen` call for this opaque-identifier privacy correction by `../direction-a/imagegen.metadata.json`. The rail visibly abstains from maximum units and purchase ceiling while parking is not hash-bound, and every visible deal/parcel identifier is an allowlisted opaque synthetic `DEAL-*` ID. Machine semantics come from the hash-bound `../direction-a/design-truth-contract.json`; prompt prose is not executable. Direction A v1 and rejected v2/v3 remain historical references only. This correction does not change the deterministic scores or selection.
