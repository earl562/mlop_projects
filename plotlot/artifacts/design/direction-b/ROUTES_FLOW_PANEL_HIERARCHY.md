# Routes, Task Flow, and Panel Hierarchy

## Route map

| Route | Stable key | Purpose | Entry condition |
| --- | --- | --- | --- |
| `/atlas` | jurisdiction + viewport | Locate/select a parcel; no feasibility claim | jurisdiction may be known or unknown |
| `/atlas/parcel/:parcelId` | canonical parcel ID | Parcel dossier summary | parcel identity resolved |
| `/atlas/parcel/:parcelId/zoning` | parcel + record version | District, use, dimensions, source excerpts | enabled coverage + retrieved record |
| `/atlas/parcel/:parcelId/constraints` | parcel + overlay snapshot | Flood/environment/access/other constraints | geometry/overlay availability reported explicitly |
| `/atlas/parcel/:parcelId/survey` | parcel + document ID | Survey/plat ledger and conflict review | source document linked or missing state |
| `/atlas/parcel/:parcelId/comps` | parcel + comp set version | Explain comparable inclusion, adjustments, and gaps | comp policy + sample set available |
| `/atlas/parcel/:parcelId/ceiling` | parcel + calculation version | Capacity assumptions and provisional purchase ceiling | capacity result is complete or has bounded unknowns |
| `/atlas/parcel/:parcelId/evidence/:evidenceId` | immutable evidence ID | Replay exact record/extraction/version | cited evidence exists |
| `/coverage` | market/city | Coverage policy and municipal condition | always accessible |

There is no `/deals`, `/pipeline`, `/assistant`, or portfolio command-center route in this direction.

## Primary task flow: verify before valuing

1. **Choose jurisdiction or paste APN/folio.** Locator recognizes format but does not imply coverage.
2. **Resolve identity.** Present one result, candidate results, or an ambiguity state. The user confirms canonical parcel identity.
3. **Inspect atlas context.** Selected geometry, source date, and active layers provide geometric orientation. A text alternative exposes the same identity.
4. **Open dossier summary.** Coverage is read before zoning. Source count and unresolved record count are visible before capacity.
5. **Read governing records.** Zoning → setbacks/dimensional rules → overlays → survey/plat. Each claim opens a replayable source item.
6. **Inspect capacity sheet.** Formula, inputs, governing constraint, and “estimate/abstain” status are visible together.
7. **Inspect purchase ceiling.** The ceiling names its capacity version, comp policy, cost assumptions, and conditions; it never appears alone.
8. **Handle a gap.** “Needs verification” opens the exact missing record request or a bounded handoff. No synthetic analysis is offered as a substitute.
9. **Share/review.** Copy a redacted dossier link or export evidence manifest; source identities and status persist with it.

## Alternate task flow: evidence replay

`Fact row citation` → `Evidence drawer` → `Source identity + retrieval version` → `record excerpt or document page` → `extraction transform` → `calculation/LLM claim that used it` → `previous/next version`. The user can return to the originating fact without losing atlas selection.

## Desktop panel hierarchy (1440×900)

```text
App shell
├─ LocatorBar (fixed 64px)
│  ├─ Brand / Atlas
│  ├─ jurisdiction control
│  ├─ APN / folio locator
│  └─ coverage / account utilities
├─ AtlasWorkspace (min-height: 0; owns remaining viewport)
│  ├─ AtlasCanvas (56–60%; scroll/zoom owner: map engine only)
│  │  ├─ selected parcel geometry
│  │  ├─ layer controls / scale / source date
│  │  └─ textual selection result list (visually adjacent, keyboard equivalent)
│  ├─ ParcelDossier (26–30%; vertical scroll owner)
│  │  ├─ identity + coverage truth (sticky inside dossier)
│  │  ├─ sheet navigation
│  │  └─ current sheet: facts / calculations / abstention
│  └─ EvidenceSpine (15–18%; vertical scroll owner)
│     └─ ordered RecordRows, each opens EvidenceDrawer
└─ EvidenceDrawer (modal on compact widths; 34% overlay on desktop)
```

Scroll contract: `AtlasWorkspace`, `ParcelDossier`, and `EvidenceSpine` use `min-block-size: 0`. The page itself does not accumulate a second vertical scroll region on desktop. The map never traps tab focus; its interaction controls are first in the map subtree and a selection results list follows it.

## Keyboard order and focus restoration

1. Skip link → LocatorBar → map controls → selection result list → dossier heading → dossier sheet tabs → current-sheet controls/fact citations → evidence rows → utilities.
2. `Enter` on candidate parcel confirms selection; focus moves to the dossier identity heading.
3. `Enter` on a citation opens `EvidenceDrawer`; focus lands on close button, then source title.
4. `Escape` closes the drawer and restores focus to the exact citation invoker.
5. Sheet change keeps focus on the active sheet heading, except when invoked by a tab keypress, where it remains on the selected tab.

## Handoff panel contract

When a fact is blocked, the dossier offers an explicit handoff rather than a generic “ask AI” action:

| Field | Example |
| --- | --- |
| Need | “Current municipal setback schedule for this zoning district” |
| Reason | “Retrieved ordinance lacks rear setback table” |
| Inputs | canonical parcel ID, zoning record E-02, date/version, missing field |
| Allowed output | cited source record or “not found” result |
| Owner | municipal research / land-use counsel / user upload |
| Result effect | unlocks a specific fact recalculation; does not retroactively alter evidence |

## Boundary behavior

- Browser Back follows source opening order: evidence replay → current dossier sheet → prior sheet → atlas query.
- Closing a conditional-market policy popover does not change selected parcel or inputs.
- Changing jurisdiction invalidates unresolved locator candidates and prompts confirmation before replacing a selected parcel.
- A direct evidence URL is read-only if the reader lacks jurisdiction/market eligibility; it can show redacted metadata but not create a derived conclusion.
