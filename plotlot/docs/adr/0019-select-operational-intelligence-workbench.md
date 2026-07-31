# ADR 0019: Select the Operational Intelligence Workbench

Status: Accepted
Date: 2026-07-26

## Context

PlotLot needs a production UI contract for acquisition and preconstruction users who must verify a parcel, establish jurisdiction and coverage, understand governing land-use constraints, derive a supportable maximum-unit case, set a provisional purchase ceiling, and route unresolved evidence without inventing certainty.

Three complete reference packets explored different home objects: an evidence-led workbench, a parcel atlas and dossier, and a role-owned stage-gate binder. The production choice must preserve evidence comprehension and coverage truth at desktop, tablet, and mobile widths without becoming a generic chat/SaaS dashboard or relying on generated raster UI.

## Decision

Adopt **Direction A — Operational Intelligence Workbench** as the authoritative product design direction.

The primary information architecture is a retained deal queue, a continuous numbered evidence ledger, and an anchored decision rail. On mobile this becomes one sequential evidence column plus a stable decision dock. Evidence precedes interpretation. Grounded model output is a small citation-bound brief, and agent activity appears as a bounded handoff with immutable inputs, owner, blocker, and expected output.

The selection is governed by `plotlot/DESIGN.md` and the deterministic artifacts under `plotlot/artifacts/design/selection/`.

Coverage remains:

- Miami-Dade: private beta.
- Broward and Palm Beach: municipality-conditional; countywide analysis is not enabled.
- San Diego: planned, not enabled.

Generated direction PNGs are non-authoritative composition references. They may not be embedded as interactive product UI or used as the source of product copy, state, facts, geometry, or accessibility.

## Consequences

The common evidence-to-decision workflow requires fewer mode changes and keeps provenance adjacent to conclusions. The system can borrow Direction C’s explicit handoff ownership and Direction B’s focused parcel-geometry inspection as secondary patterns without adopting their primary navigation models.

The current landing/workspace token split, national availability copy, generic welcome composer, missing evidence anatomy, off-canvas mobile controls, and narrow placeholder clipping become implementation gaps for Todo21. This ADR does not authorize frontend source changes.

Map exploration becomes a focused supporting route rather than the home surface. Formal approvals remain auditable handoff/decision records rather than the global navigation metaphor. A dark operational theme is not part of this contract.

## Rejected alternatives

**Parcel Atlas and Evidence Dossier.** Strong for geometry and record exploration, but the map consumes the dominant surface and adds keyboard, reflow, and mode-switching cost to the common evidence-to-decision job.

**Preconstruction Deal Room and Stage-Gate Binder.** Strong for accountability and review, but its gate metaphor partitions the current decision and adds navigation overhead. Its handoff anatomy is retained as a component pattern.
