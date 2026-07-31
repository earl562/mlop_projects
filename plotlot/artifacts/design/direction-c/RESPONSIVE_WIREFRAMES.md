# Responsive Wireframes and Content-Stress Contract

## 1440×900 — full binder

```text
┌──────────────────────────────── Utility header: deal • coverage • replay • profile ────────────────────────────────┐
├──────────── Binder spine 248 ────────────┬──────────────── Current gate dossier, flexible ──────────────┬─ Handoff 328 ─┤
│ 01 Intake thesis              approved   │ Northwest infill — review binder                              │ OWNER           │
│ 02 Jurisdiction & rules       approved   │ Gate 03 Capacity & site · Exit: current cited inputs          │ Preconstruction │
│ 03 Capacity & site            CURRENT    │ [Folio/APN] [Miami-Dade private beta] [RU-2]                  │ SLA / blocker   │
│ 04 Basis & ceiling            waiting    │                                                                    │                 │
│ 05 Review decision            locked     │ Capacity worksheet: lot area → setbacks → parking → max units │ HANDOFF         │
│                                          │ Governing constraint: lot area · Max units: 2                  │ Inputs 7        │
│ Gate history / returned note              │ Constraints · Survey/plat v2 · Comps / exclusion reasoning     │ Output: review  │
│                                          │ Purchase ceiling $418,000 [replay]                             │                 │
│                                          │ Grounded analysis: cited claim / abstain parking rule          │ APPROVAL LINE   │
│                                          │ Evidence packet index                                           │ Request review  │
└──────────────────────────────────────────┴──────────────────────────────────────────────────────────────┴─────────────────┘
```

- Header fixed; binder, dossier, and rail have named vertical scroll ownership.
- Dossier has minimum inline size `minmax(520px, 1fr)` and uses a max 76ch prose measure. Rail does not squeeze rule values below readable width.
- Tables use a four-column worksheet only while each source/value/formula cell retains 12ch minimum; then collapse into labelled vertical rows.
- Current tab: 2px focus/outlining + text status; not color alone. The gate has no auto-advancing animation.

## 768×1024 — inspector binder

```text
┌──────────────────────── Header: deal switcher • coverage • overflow ────────────────────────┐
├──── Binder 214 ────┬────────────────────────── Dossier, remaining width ─────────────────────┤
│ 01 Intake          │ Gate 03 Capacity & site                                                 │
│ 02 Rules            │ decision / exit criterion                                               │
│ 03 Capacity CURRENT │ identity + coverage                                                     │
│ 04 Basis            │ capacity worksheet (labelled rows)                                      │
│ 05 Review           │ constraints / survey / comps / ceiling / grounded brief                 │
│                     │ [Open handoff & approvals]                                               │
└─────────────────────┴────────────────────────────────────────────────────────────────────────┘
                             ↳ Handoff opens as modal sheet; focus trapped and restores on close
```

- The persistent right rail is replaced by a single explicit `Open handoff & approvals` button after dossier content; it preserves DOM reading order.
- Gate labels may wrap to two lines; metadata moves below title rather than compressing to unreadable text.
- Dossier owns scrolling; binder tabs own scrolling only if needed. Header controls compact into labelled overflow menu.

## 390×844 — sequential review packet

```text
┌──────────────────────────────────── 52px header ───────────────────────────────────┐
│ Back · Northwest infill (truncated visually, full accessible name) · menu           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Gate 03 of 05 · Capacity & site · Waiting for parking rule                           │
│ [Change gate]                                                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Exit criterion                                                                       │
│ Current source-bound rules + reviewed survey/plat + resolved governing constraint    │
│                                                                                       │
│ Parcel / coverage                                                                    │
│ FOLIO 30-3115-•••-0420 · Miami-Dade private beta                                    │
│                                                                                       │
│ Capacity worksheet                                                                   │
│ Lot area … cited value                                                               │
│ Setbacks … cited values                                                              │
│ Parking … MISSING → MAX UNITS — ABSTAINED                                            │
│                                                                                       │
│ [Survey / plat packet] [Constraints] [Comps / basis]                                 │
│ Grounded analysis — abstained: parking rule is not hash-bound                        │
│ [Replay evidence] [Open handoff]                                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Fixed decision dock: BLOCKED · Resolve parking rule                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- One document scroll owner. The `Change gate` control opens a labelled bottom sheet; it does not turn the page into a horizontally scrolling tab rail.
- 16px gutters; 44×44px interactive hit targets; 84px bottom padding protects the last field from the 68px dock.
- Money, max units, APN/folio, blocker, and coverage status never truncate. Long hashes wrap at any character with a copy button.
- Any modal/bottom sheet honors safe-area inset and has visible close, Escape (where keyboard exists), focus return, and no background scroll.

## Content-stress / overflow matrix

| Stressor | 1440 | 768 | 390 |
|---|---|---|---|
| 64-char source hash | technical column wraps anywhere | wraps below source label | wraps below label with copy affordance |
| 3+ source conflicts | compare rows with disclosure | stacked conflict packets | one-by-one disclosure; conflict summary remains above fold |
| 12 linked documents | scroll list with filter | filter then sheet | sequential list with type/date/filter sheet |
| 8-line reviewer return | rail scrolls independently | modal sheet scrolls | expands in document flow; dock remains unobscuring |
| long municipality name | metadata row below deal title | same | separate metadata row, full name available to AT |
| unavailable purchase ceiling | explicit reason, no blank tile | same | dock says unavailable + blocker; no zero or guessed value |
| 200% zoom | 3 columns may become 2 then linearize | linearizes | remains single column, no x-scroll |
