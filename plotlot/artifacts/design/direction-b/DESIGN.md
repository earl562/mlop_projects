# Design Contract — Direction B: Parcel Atlas / Evidence Dossier

## 0. Design decision

Direction B is a **parcel ledger laid over a cadastral map**. The remembered moment is selecting a polygon and seeing a quiet “evidence thread” lock to the same APN/folio: every capacity figure, constraint, and dollar conclusion points back to a source record or names its absence.

The visual reference was generated once with the versioned prompt at `../direction-b.prompt.md`. It informed material and hierarchy only; it does not establish product facts or responsive behavior.

## 1. Interface signature and usage

```ts
type ParcelLocator = {
  jurisdictionId: string;
  parcelId?: string;       // authority-specific canonical id
  apn?: string;
  folio?: string;
  geometryHint?: GeoJSON.Polygon;
};

type DossierOpen = {
  locator: ParcelLocator;
  view: "summary" | "zoning" | "constraints" | "survey" | "comps" | "ceiling" | "evidence";
  evidenceCursor?: string;
};

type EvidenceClaim<T> = {
  value?: T;
  status: "verified" | "derived" | "needs_verification" | "conflict" | "unavailable" | "not_enabled";
  citations: readonly string[];
  computedAt?: string;
  reason?: string;
};

interface ParcelAtlas {
  locate(input: ParcelLocator): Promise<EvidenceClaim<ParcelSummary>>;
  open(input: DossierOpen): Promise<ParcelDossier>;
  replay(evidenceId: string): Promise<EvidenceReplay>;
}
```

```ts
const parcel = await atlas.locate({ jurisdictionId: "miami_dade", folio: "30-••••••-••••" });
if (parcel.status !== "verified") showResolutionState(parcel);
else openDossier({ locator: parcel.value.locator, view: "zoning" });
```

This small public shape hides geocoding normalization, assessor joins, jurisdiction resolution, source retrieval, deterministic capacity calculations, and citation graph construction. Callers never ask an LLM to “look up a property” and never receive an un-cited feasibility answer.

## 2. Design tokens

| Token | Value / use |
| --- | --- |
| `--paper-0` | `#F7F4EE`; main dossier ground |
| `--paper-1` | `#ECE8DF`; atlas grid/quiet fills |
| `--ink-0` | `#172630`; primary text, parcel outline |
| `--ink-1` | `#405560`; secondary labels |
| `--atlas-blue` | `#315C78`; selected geometry, verified citations, links |
| `--copper-600` | `#A7552B`; needs-verification/warning only |
| `--moss-600` | `#466353`; verified record indicator only |
| `--rule` | `#C9C4B8`; 1px divisions |
| `--focus` | `#0B5E8E`; 3px outer focus ring, 2px offset |
| `--shadow-dossier` | `0 1px 0 rgb(23 38 48 / .08), 0 12px 28px rgb(23 38 48 / .06)`; only for raised mobile drawer |
| `--font-display` | `"Source Serif 4", Georgia, serif`; identity/APN/fact emphasis |
| `--font-ui` | `"IBM Plex Sans", ui-sans-serif, sans-serif`; controls/body |
| `--font-mono` | `"IBM Plex Mono", ui-monospace, monospace`; evidence IDs, hashes, formula inputs |
| `--space-1…8` | 4, 8, 12, 16, 24, 32, 48, 64px; no arbitrary spacing |
| `--radius-1` | 4px; controls/record rows only; panels are primarily ruled, not pill-shaped |

## 3. Typography and density

- Parcel canonical ID: Source Serif 4, 28/32 desktop; 23/28 mobile; `font-variant-numeric: tabular-nums`.
- Dossier title: Source Serif 4, 20/26; it never exceeds two lines at any specified viewport.
- Section headings: Plex Sans, 12/16, 600, sentence case; no cheap numbered meta-labels.
- Factual values: Plex Sans 14/20; numeric cells use tabular figures.
- Provenance/source IDs: Plex Mono 11/16, wrap at delimiter opportunities; never forced into horizontal scrolling.
- Long label constraint: map labels truncate after 24 characters with accessible full name in `aria-label`; record titles wrap to two lines before the source rail grows vertically.

## 4. Material and visual grammar

Warm paper grounds the dossier; low-contrast parcel geometry grounds the atlas; thin rules establish archival order. Selected geometry uses a dark-blue outline and a 12% blue fill. Verified information uses blue text plus a named text state—never color alone. Copper appears only when a record is missing, conditional, stale, or conflicts; it is never a decorative accent. There is no gradient hero, glass blur, neon, photo-real estate imagery, or forced “AI” glow.

## 5. Primitives and semantic states

| Primitive | Anatomy | Required states |
| --- | --- | --- |
| `ParcelLocator` | jurisdiction selector, APN/folio/search input, resolve action | empty, parsing, resolved, ambiguous, outside-coverage, error |
| `AtlasCanvas` | basemap, parcels, selected geometry, scale, source date, layer control | neutral, selected, geometry-unavailable, reduced-detail |
| `ParcelDossier` | identity header, coverage truth, section list, current sheet | loading, verified, partial, conflict, not-enabled |
| `FactRow` | label, value/range, status label, citations | verified, derived, needs-verification, conflict, unavailable |
| `RecordRow` | authority, record title/version, retrieved date, status, replay control | current, stale, missing, conflicting, blocked |
| `EvidenceDrawer` | excerpt, source identity/hash, extraction/replay metadata, adjacent versions | closed, open, loading, unavailable |
| `CalculationSheet` | formula, locked inputs, result/range, governing constraint, citations | complete, incomplete, conflicting, not-applicable |
| `AbstentionNotice` | bounded claim, reason, allowed next action | conditional-market, missing-record, conflict, planned-market |
| `GroundedBrief` | cited observations, unknowns, next evidence request | supported, partial, abstains, failed-citation-check |

## 6. Interaction rules

- Selecting a parcel updates the dossier and evidence rail atomically. The previous dossier remains visually marked as stale until the new selection resolves; it is never silently replaced.
- Hover on a parcel only reveals an APN/folio tooltip; click/keyboard selection is required to change context.
- Every derived fact opens its calculation sheet. Every source chip opens the exact evidence replay, not a generic document browser.
- Filtering map layers never removes the selected parcel outline. If a required layer is unavailable, the layer control says so and the related facts become unavailable/needs verification.
- Coverage badges open a concise policy popover with `market`, `authority`, and `scope`, not sales copy.
- Motion is limited to 140–180ms opacity/transform transitions for sheet/drawer entry and source-row expansion. `prefers-reduced-motion: reduce` makes those immediate and disables map fly-to animation.

## 7. Accessibility and input contract

- All map selection actions have an equivalent keyboard-accessible results list, ordered by the same queried APN/folio.
- The map exposes a textual selected-parcel summary; non-text geometry is supplemental, not the only carrier of legal identity.
- Focus moves to `ParcelDossier` heading after a confirmed selection and returns to the invoking result after close/back.
- Dossier sheet tab buttons use native buttons with `aria-selected`, `aria-controls`, and visible focus.
- Record rows remain buttons rather than nested links; the replay drawer receives focus only on explicit invocation.
- Status icons are paired with text (“Verified”, “Needs verification”, “Conflict”, “Not enabled”). Contrast targets are 4.5:1 normal / 3:1 non-text boundary.
- Full map operations work through pointer, keyboard, and 200% zoom without requiring drag gestures.

## 8. Deliberate tradeoffs and accepted debt

- The atlas gives less immediate comparison breadth than a pipeline. That is deliberate; a future portfolio route may link into this dossier by canonical parcel ID.
- Satellite, street imagery, and enrichment are intentionally absent from the primary canvas. They risk false confidence and distract from authority/source age.
- First release does not claim automated parcel-boundary certainty where public records disagree. It shows an ambiguity state and preserves candidate IDs.
- Claims are information design, not advice: product copy must retain “estimate”, “recorded”, “derived”, and “needs verification” distinctions.
