# Routes, flow, and panel hierarchy

Direction A is one evidence-first workbench, not a collection of modes. The active deal and the decision statement remain coherent while a user drills into an evidence row or a focused secondary route.

## Route map

| Route | Purpose | Entry | Return / guard |
|---|---|---|---|
| `/workbench/:dealId` | Default acquisition and preconstruction decision surface | Deal queue, deep link, resolved lookup | Always available once a redacted deal shell exists |
| `/workbench/:dealId/evidence/:evidenceId` | Focused evidence disclosure, source excerpt, and replay metadata | Ledger row / citation link | Back returns to the same row and its disclosure state |
| `/workbench/:dealId/documents/:documentId` | Survey, plat, construction, or legal-document inspection | Document evidence row | Missing/corrupt documents show their artifact state; never invent an extraction |
| `/workbench/:dealId/constraint/:constraintId` | Constraint formula and inputs | Governing-constraint link | Provisional or missing inputs keep result explicitly abstained |
| `/workbench/:dealId/comps` | Comparable-selection logic and adjustment basis | Comps ledger row | Comps are evidence only; they do not override a blocked capacity case |
| `/workbench/:dealId/underwriting` | Purchase-ceiling assumptions and sensitivity | Underwriting row | Disabled when required capacity or parking evidence is unresolved |
| `/workbench/:dealId/replay/:runId` | Immutable evidence/replay record | Provenance row | Read-only; hash mismatch blocks derived-claim reuse |
| `/coverage` | Coverage gate and municipality selection | Coverage row / unavailable deal | Never promotes conditional or planned areas to enabled analysis |

Focused routes retain the same deal context and return to `/workbench/:dealId`; none replace the workbench with a map-first, file-browser, or chat-first primary experience.

## Common-case acquisition flow

1. Select a retained or newly resolved parcel in the deal queue.
2. Confirm parcel/folio or APN and jurisdiction before any rule result is shown.
3. Read the coverage gate. Miami-Dade private beta may continue; Broward and Palm Beach stop at municipality selection; San Diego County remains planned/not enabled.
4. Walk the ordered evidence ledger: zoning, setbacks/dimensional rules, overlays, capacity, documents, comps, underwriting, and provenance.
5. Open the governing constraint to inspect inputs, formula, ordinance citations, and the hash-bound source artifacts.
6. Read the decision rail: maximum units, governing constraint, purchase ceiling, completeness, grounded brief, and blocker.
7. If a required fact is unresolved, use **Resolve blocker** to create a bounded handoff. The UI does not offer a confident recommendation around missing evidence.
8. Replay the run from provenance before a material decision or handoff.

## Desktop panel hierarchy — 1440×900

```text
WorkbenchShell (bounded to 100dvb)
├─ UtilityHeader (56px, fixed)
│  ├─ PlotLot / active deal context
│  └─ Search, notes, exports, alerts, settings
└─ WorkbenchBody
   ├─ DealQueue (256px; its list scrolls)
   │  ├─ Deal rows
   │  └─ Coverage gate
   ├─ EvidenceSpine (flexible; primary scroll owner)
   │  ├─ Parcel identity + jurisdiction/coverage
   │  ├─ Evidence ledger, ordered 1–10
   │  └─ Time / source freshness footer
   └─ DecisionRail (344px; sticky, scrolls only if needed)
      ├─ Max units / governing constraint / purchase ceiling
      ├─ Evidence completeness
      ├─ Grounded opportunity brief
      ├─ Blocker
      └─ Agent handoff + Resolve blocker
```

The evidence spine owns the visual center and the widest measure. The decision rail is a consequence surface, not a dashboard of equal-weight cards. A small parcel-outline thumbnail may live in parcel identity; no large map is shown.

## Keyboard and focus order

1. Skip link to evidence spine.
2. Utility header controls, left to right.
3. Deal queue filter and deal rows.
4. Parcel identity and coverage gate.
5. Ledger disclosures in ordinal order; within an expanded row: source/citation, copy-hash, replay link, related claim.
6. Decision rail: decision summary, claim citations, blocker, handoff, primary action.
7. Footer freshness / replay metadata.

Focus never jumps to a live update. Activating a citation moves focus to its evidence row only on explicit request, preserves a visible return control, and keeps the rail decision in DOM order after the evidence spine.

## Scroll, disclosure, and action rules

- Desktop/tablet: queue, spine, and rail are the only named scroll owners. Use `min-block-size: 0` on each bounded child.
- Mobile: one document scroll owner; the decision dock is fixed and reserves bottom scroll padding.
- Disclosure expands inline inside its current owner. It does not open a modal by default.
- **Resolve blocker** opens a structured handoff sheet with the exact missing fact, accepted evidence, owner, and expected output; it is not a generic chat composer.
- Citation trace is the signature interaction: focus or activation quietly marks the cited ledger rows and their source IDs. Reduced motion makes the state change immediate.
