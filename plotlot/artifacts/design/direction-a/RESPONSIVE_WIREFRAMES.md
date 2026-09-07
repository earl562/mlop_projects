# Responsive wireframes and content-stress specification

All examples use redacted illustrative fixtures. Rows are semantic containers, not fixed-height screenshots; text may grow without clipping. No primary decision path requires horizontal scrolling.

## 1440×900 — three-panel workbench

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 56px utility header: PlotLot | active deal | search | notes | export | alerts | settings                     │
├───────────────256──────────────┬──────────────────── flexible evidence spine ─────────────────────┬──344─────┤
│ DEAL QUEUE                     │ 12•• NW 67 ST · UNINCORPORATED MIAMI-DADE                       │ DECISION │
│ active / retained deals         │ FOLIO 30-3115-•••-0420 · Miami-Dade private beta                │ Max units│
│                                 ├─────────────────────────────────────────────────────────────────┤ 2        │
│ Coverage gate                   │ 1 Parcel identity        verified · citation · hash             │ Constraint│
│ Miami-Dade private beta         │ 2 Jurisdiction/coverage   verified · citation · hash             │ Lot area │
│ Broward municipality required   │ 3 Zoning                  RU-2 · citation · hash                 │ Ceiling  │
│ Palm Beach municipality req.    │ 4 Setbacks/dimensional    inputs · citation · hash               │ $418,000 │
│ San Diego planned/not enabled   │ 5 Overlays/constraints    focus-visible disclosure               │ Evidence │
│                                 │ 6 Capacity/max units      formula + governing marker              │ 6/7      │
│                                 │ 7 Survey/plat/docs        document version + hash                 │ Brief    │
│                                 │ 8 Comps                   inclusion logic                         │ Blocker  │
│                                 │ 9 Underwriting            conditional scenario                    │ Handoff  │
│                                 │10 Provenance              replay root                              │ Resolve  │
└─────────────────────────────────┴─────────────────────────────────────────────────────────────────┴──────────┘
```

- Header is fixed. The body is `calc(100dvb - 56px)`; queue and spine scroll independently, rail only if overflowed.
- Minimum spine width is 560px. If it cannot be maintained, change to the tablet composition rather than squeeze the ledger.
- Ledger columns may collapse metadata beneath the row title, but citation/hash stays in the same row and remains reachable.
- Rail stays visually anchored and begins with the decision summary; it never overlays evidence scrollbars.

## 768×1024 — evidence + persistent rail

```text
┌────────────────────────────────────────────────────────────────────┐
│ 56px header: deal switcher · search · alerts · overflow             │
├───────────────────────────────────────────────┬────────────────────┤
│ Evidence spine (min 500px; primary scroll)    │ Decision rail 268px│
│ Parcel + coverage                              │ 2 units            │
│ Ledger rows: title/value first, source below   │ lot area            │
│ Row disclosure is inline                       │ $418,000 conditional│
│ Documents / comps / provenance                 │ 6/7 · brief · block │
│                                                 │ Resolve blocker     │
└───────────────────────────────────────────────┴────────────────────┘
```

- Deal queue becomes a header switcher/slide-in list; it does not steal horizontal space.
- Evidence row source/citation/hash moves to a second line before the title/value becomes too narrow.
- Rail is 268px and may scroll only within its own region. Max units, governing constraint, ceiling, completeness, blocker, and action stay above any optional prose.
- At 200% zoom or when the 500px spine is no longer viable, use the mobile single-column composition.

## 390×844 — sequential evidence with fixed decision dock

```text
┌──────────────────────────────────────┐
│ 52px header: deal switcher · actions  │
├──────────────────────────────────────┤
│ 12•• NW 67 ST                         │
│ FOLIO 30-3115-•••-0420                │
│ Miami-Dade private beta               │
├──────────────────────────────────────┤
│ Acquisition decision                  │
│ 2 units · lot area · $418,000*        │
│ *Conditional: parking evidence absent │
├──────────────────────────────────────┤
│ 1 Parcel identity                     │
│   source/citation/hash                │
│ 2 Jurisdiction + coverage             │
│ 3 Zoning                              │
│ … sequential ledger                   │
│ 10 Provenance / replay                │
│ Grounded brief / blocker / handoff    │
│ (bottom scroll padding ≥ 84px)        │
├──────────────────────────────────────┤
│ Fixed 68px dock: Conditional · Resolve│
└──────────────────────────────────────┘
```

- One document scroll owner; no nested scroll panels.
- Property identity and coverage precede the compact decision summary. The full rail content appears after the ledger and before replay metadata.
- Decision dock is 68px with a 44×44px action target; it never auto-hides or covers focused content. It uses “Unavailable” rather than a clipped number when the rail is abstained.
- Each ledger row is at least 72px and disclosure content stacks: value, status text, citation, then hash. Long technical values use `overflow-wrap:anywhere`; ordinary prose uses natural word wrapping.
- In an unsupported state, the dock says “Analysis unavailable” and offers “View coverage,” not “Resolve blocker.”

## Overflow, zoom, and state stress

| Stress case | Required behavior |
|---|---|
| 64-character SHA-256 | Wrap anywhere; preserve copy control and full accessible label |
| Long legal description / municipality | Move locality to metadata, then disclose full content; never clip primary parcel ID |
| Two governing constraints tie | Render two named governing rows and a blocked/conditional capacity result |
| Five document versions | Keep current version in row; expose history inline/secondary route with version dates |
| 200% zoom or 320px width | Switch from columns to stacked labels; all action targets and decision copy remain visible |
| Offline/stale refresh | Preserve last known artifact with timestamp and stale label; do not silently show it as verified |
| Screen reader / keyboard | DOM order remains header → evidence → decision detail → dock; visual stickiness does not reorder content |
| Reduced motion | Disclosure/citation state changes happen immediately; no shimmer, parallax, or auto-scroll |
