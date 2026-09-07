# Responsive Wireframes and Content-Stress Specification

## 1440×900 — Atlas + dossier + evidence spine

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PlotLot / Atlas     [Miami-Dade ▾] [APN / folio / parcel lookup________________] [Coverage] [Utilities]     │ 64
├──────────────────────────────────────┬─────────────────────────────────────┬───────────────────────────────┤
│                                      │ Parcel dossier                       │ Evidence replay               │
│          CADASTRAL ATLAS             │ APN / folio (canonical identity)     │ E-01 Survey / plat            │
│          selected parcel outline     │ Coverage truth                        │ E-02 Zoning record            │
│          layer + scale + source age  │ ─ summary / zoning / constraints ─   │ E-03 Dimensional schedule     │
│                                      │ zoning / setbacks / capacity          │ E-04 Flood layer               │
│  keyboard-equivalent result list     │ survey / comps / ceiling              │ E-05 Tax / deed               │
│                                      │ grounded brief / abstention           │ Needs verification row         │
├──────────────────────────────────────┴─────────────────────────────────────┴───────────────────────────────┤
│ selected source set · coordinate system · data age · “dimensions require confirmation”                       │ 44
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  56–60% atlas (806–864px)                 26–30% dossier (374–432px)        15–18% evidence (216–259px)
```

- The identity header is sticky within the dossier, not globally fixed.
- Evidence spine is ordered by use in the active sheet; a persistent filter can show all records.
- Dossier and evidence panes scroll independently; map gesture handling is opt-in after focus/click.
- `EvidenceDrawer` opens as a 480px overlay over the evidence spine/dossier edge and never covers the selected parcel entirely.

## 768×1024 — Atlas band + dossier body

```text
┌──────────────────────────────────────────────────────────┐
│ PlotLot  [Jurisdiction] [APN / folio] [Coverage] [Menu]   │ 64
├──────────────────────────────────────────────────────────┤
│ CADASTRAL ATLAS  | selected parcel label | layers | scale │ 288
│ (result list follows map; no hidden map-only selection)   │
├──────────────────────────────────────────────────────────┤
│ APN / folio · Coverage truth · record-count status        │
│ [Summary] [Zoning] [Constraints] [More ▾]                 │
│ current sheet facts / capacity / abstention               │
│ source citations open a right-side drawer                 │
├──────────────────────────────────────────────────────────┤
│ Evidence  7 verified · 1 needs verification  [Open]       │ 56
└──────────────────────────────────────────────────────────┘
```

- Map is an approximately 288px-tall context band; dossier owns the remaining document scroll.
- Dossier section tabs are horizontally scrollable only as a native, focus-visible tab list with scroll buttons; never clipped/faded without a discoverable control.
- Evidence uses a 56px summary shelf. Opening it creates a 420px wide side drawer where space permits, otherwise a modal sheet with close/back and focus trap.
- Capacity and purchase ceiling appear only after zoning/constraints summary; the reading sequence is source → constraint → calculation.

## 390×844 — Parcel dossier first, map on demand

```text
┌──────────────────────────────────────┐
│ PlotLot         [Search] [Coverage]  │ 56
├──────────────────────────────────────┤
│ Miami-Dade private beta               │
│ APN / folio 30-••••••-••••  [Change]  │
│ Parcel status: 7 records · 1 gap      │
├──────────────────────────────────────┤
│ [Summary] [Zoning] [Constraints]      │ 44
├──────────────────────────────────────┤
│ Current sheet                         │
│ Zoning + authority                     │
│ Setbacks / constraints                 │
│ Capacity / “Needs verification”        │
│ citations: E-02 · E-03                 │
├──────────────────────────────────────┤
│ [Map]  [Evidence 8]  [Ceiling]        │ 56 fixed bottom actions
└──────────────────────────────────────┘
```

- The mobile entry is the identity/coverage dossier. This preserves the direction’s parcel-first model rather than shrinking desktop panels.
- `Map` opens a full-height sheet with a visible text result list and “Return to dossier” action; selection changes require confirmation.
- `Evidence` opens a full-height sheet in source order, with citation deep links and exact replay metadata. It does not launch a generic file browser.
- `Ceiling` opens only if not disabled by upstream state; otherwise its action is replaced by `Resolve gap` with the named blocker.
- The lower action bar uses safe-area inset padding. Content receives bottom padding equal to bar height + `--space-4`.

## Breakpoint rules

| Rule | Wide | Medium | Narrow |
| --- | --- | --- | --- |
| Shell | three columns | map band + dossier | dossier, sheets for map/evidence |
| Canonical identity | header inside dossier | full-width dossier header | top dossier header before tabs |
| Map controls | left rail | top/right condensed | sheet toolbar, no drag-only action |
| Evidence | persistent spine | summary shelf + drawer | full-height sheet |
| Comparison tables | four fact cells per row | two-by-two fact grid | label/value stacked rows |
| Long IDs | mono wrap at separators | mono wrap at separators | copied in a separate full-width field |
| Source title | single line + ellipsis | two lines | two lines + 44px minimum hit target |

## Overflow and stress cases

1. **Folio longer than 32 glyphs:** show the canonical value in a wrapping mono block; retain a discrete copy button and do not use ellipsis for legal identity.
2. **Ten evidence records:** rail/drawer scrolls internally; summary keeps verified/gap counts. No full page reflow on record expansion.
3. **Three conflicting zoning sources:** rows group beneath one conflict notice; capacity block is replaced with abstention, not pushed off screen.
4. **Long municipality name:** selector truncates visibly only after the meaningful city token; accessible name retains full text and the coverage policy opens in a sheet.
5. **200% browser zoom / 320 CSS px:** the application becomes the mobile single-column view; no two-pane minimum width survives.
6. **Map load error:** preserve dossier/context; map sheet announces failure and offers retry, but no zoning or constraints value is inferred from the blank canvas.

## Motion/reduced-motion spec

- Selection confirmation: 160ms opacity/transform only; no camera flight required.
- Dossier sheet and evidence drawer: 180ms transform/opacity; do not animate height/width.
- `prefers-reduced-motion: reduce`: settle instantly, remove map fly-to, preserve all state changes and focus movement.
