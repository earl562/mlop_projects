# PlotLot Direction A Design System

## 0. Research log and deterministic selection

- Product contract: PlotLot’s `Lookup` lane prioritizes resolved parcel/jurisdiction, zoning, dimensional rules, maximum units, governing constraint, sources, confidence, and freshness before optional comps, pro forma, documents, and strategy.
- Embedded references shortlisted: Linear for precise hierarchy and luminance stepping; Sentry for data-density discipline; Wired for ledger-like editorial scanning. Linear was selected only as the structural benchmark. PlotLot does not inherit Linear’s brand, dark marketing canvas, Inter typography, purple accent, or marketing layout.
- Layer A constraint: the requested gpt-taste selection was applied only to compatible workbench decisions. AIDA, hero architecture, cinematic section spacing, marquees, testimonial carousels, decorative scroll scenes, and generic landing-page motion were rejected as category errors.
- App-shell mechanics: fixed utility header; one named scroll owner per region; no document-level horizontal scroll; intrinsic reflow at narrow widths.
- ImageGen privacy correction: exactly one fresh built-in `image_gen.imagegen` `ui-mockup` call was made on 2026-07-27 UTC from canonical prompt `direction-a/v1.2.0`; selected output `reference-direction-a-v4.png`. Its decision rail visibly abstains from both maximum units and purchase ceiling because parking is not hash-bound, while all deal and parcel identifiers are opaque synthetic `DEAL-*` IDs. v2 and v3 are historical rejected outputs. The tool-scoped output name, prompt hash, timestamp, output hash, dimensions, generation history, and machine truth-contract hash are bound in `imagegen.metadata.json`.
- Machine semantics: `design-truth-contract.json` is the versioned, hash-bound source for state IDs, abstention dependencies, scenario/current-value separation, coverage IDs, and privacy rules. The ImageGen prompt remains hash-bound generation input and is never parsed as executable contract prose.
- External visual research: not used. This is a constrained sibling direction with an already-specified operational thesis; outside screen harvesting could collapse its distinction from map-first or deal-room lanes.

### Deterministic gpt-taste record

Seed source: full UTF-8 bytes of `../direction-a.prompt.md`.

```text
prompt characters: 5867
prompt sha256: 5a719e1b805562486e691a6a65310fce135fbf2a4dfe4101ede276d4ab9fc510
seed: integer value of sha256[0:16]
selected structure: Constraint ladder workbench
selected components: Agent handoff strip; Constraint ladder; Decision rail
selected motion: Verified-row settle; Citation trace highlight
raw typography draw: Outfit + JetBrains Mono
compatibility override: Geist + Geist Mono, because the established PlotLot type system and generated-reference prompt already bind those families
```

The deterministic draw is recorded rather than silently cherry-picked. The typography draw was intentionally overridden by the Design System Gate: an established product type stack is more important than novelty.

## 1. Atmosphere and identity

PlotLot Direction A feels like a land-use analyst’s evidence desk after the paper has been organized: calm, precise, sequential, and consequential. It is neither a control-room dashboard nor a luxury real-estate brochure. The signature is a continuous numbered evidence ledger whose rows feed an anchored decision rail. Paper-toned surfaces and ink-like typography create a case-file character; moss, ochre, and brick communicate evidence meaning rather than decoration.

The memorable moment is a citation trace: focusing a supported conclusion quietly highlights the exact evidence rows and hash-bound source IDs that make the conclusion supportable.

## 2. Color

### Palette

| Role | Token | Value | Usage |
|---|---|---:|---|
| Canvas | `--surface-canvas` | `#F4F1EA` | Workbench background |
| Panel | `--surface-panel` | `#FBFAF6` | Evidence and decision surfaces |
| Recessed | `--surface-recessed` | `#ECE9E1` | Queue filters, closed evidence subrows |
| Raised | `--surface-raised` | `#FFFFFF` | Popovers and inline disclosures only |
| Ink | `--text-primary` | `#17211D` | Primary text |
| Muted ink | `--text-secondary` | `#59655F` | Secondary text and captions |
| Quiet ink | `--text-tertiary` | `#747D78` | Timestamps, disabled-supporting copy |
| Rule | `--border-default` | `#D3D1C9` | Panel and row boundaries |
| Quiet rule | `--border-subtle` | `#E4E1D9` | Interior separators |
| Verified | `--status-verified` | `#285A46` | Verified evidence and available action |
| Verified wash | `--status-verified-bg` | `#E5EEE8` | Selected verified context |
| Conditional | `--status-conditional` | `#8A5718` | Municipality-dependent and blocked |
| Conditional wash | `--status-conditional-bg` | `#F5E9D5` | Conditional context |
| Conflict | `--status-conflict` | `#943F34` | Conflicts, invalid evidence, destructive |
| Conflict wash | `--status-conflict-bg` | `#F4E2DF` | Conflict context |
| Informational | `--status-info` | `#536B78` | Source links, neutral information |
| Focus | `--focus-ring` | `#284F73` | Keyboard focus only |
| Disabled | `--status-disabled` | `#8C928F` | Planned/not-enabled controls |

### Color rules

- Status meaning is never color-only. Every state pairs color with icon, label, and explanatory copy.
- Verified green does not mean “legally approved”; it means the displayed evidence artifact passed the product’s provenance checks.
- Ochre means conditional, unresolved, missing, or user action required. It is not used for decorative warmth.
- Brick means conflict, invalidation, or unsafe reliance.
- Blue-gray is reserved for links, focus, and neutral information; it is never the brand’s dominant fill.
- The default theme is light because evidence comparison and document reading dominate. A dark theme is out of scope for this contract.
- No gradient text, neon glow, glassmorphism, beach palette, or luxury gold.

## 3. Typography

### Families

- Primary: `Geist`, `ui-sans-serif`, `system-ui`, sans-serif
- Technical: `Geist Mono`, `ui-monospace`, `SFMono-Regular`, monospace
- No display serif in the workbench. Instrument Serif may remain in PlotLot marketing surfaces but does not enter this decision UI.

### Scale

| Role | Desktop / tablet / mobile | Weight | Line height | Tracking | Max lines |
|---|---|---:|---:|---:|---:|
| Decision title | `28 / 26 / 24` | 560 | 1.15 | `-0.02em` | 2 |
| Property title | `24 / 22 / 20` | 580 | 1.2 | `-0.015em` | 2 |
| Section heading | `18 / 18 / 17` | 580 | 1.3 | `-0.01em` | 2 |
| Evidence row title | `15 / 15 / 15` | 560 | 1.35 | `-0.005em` | 2 |
| Body | `14 / 14 / 15` | 400 | 1.5 | normal | unrestricted |
| Body compact | `13 / 13 / 14` | 400 | 1.45 | normal | 3 before disclosure |
| Label | `12 / 12 / 12` | 560 | 1.35 | `0.035em` | 2 |
| Micro metadata | `11 / 11 / 12` | 450 | 1.4 | `0.015em` | 2 |
| Technical value | `13 / 13 / 13` mono | 500 | 1.4 | `-0.01em` | 2 |
| Major money / units | `30 / 28 / 26` mono | 560 | 1.05 | `-0.025em` | 1 |

Values are pixels at the named target viewport. Implementation should encode the scale as rem-based tokens.

### Typography rules

- A property heading may wrap to two lines; if a municipality or address would create a third line, the locality moves to its own metadata row.
- No heading may exceed three lines at any supported width. Two lines is the intended ceiling; three is accepted only for user-provided long legal descriptions on mobile.
- Folio, APN, ordinance section, citation ID, source hash, timestamps, units, formulas, and money use the technical family.
- Uppercase is reserved for short labels and jurisdiction/status strings. Sentence text is not forced uppercase.
- Truncation never hides the only instance of a parcel ID, blocker, status, or monetary decision. Those values wrap or disclose in full.

## 4. Spacing and layout

### Base and tokens

Base unit: 4px.

| Token | Value | Use |
|---|---:|---|
| `--space-1` | 4px | Icon/label micro gap |
| `--space-2` | 8px | Inline metadata |
| `--space-3` | 12px | Compact row gap |
| `--space-4` | 16px | Row/panel padding |
| `--space-5` | 20px | Comfortable control group |
| `--space-6` | 24px | Panel header and section interval |
| `--space-8` | 32px | Major evidence group separation |
| `--space-10` | 40px | Empty state breathing room |
| `--space-12` | 48px | Mobile decision-section break |

### Geometry

- Utility header: 56px desktop/tablet; 52px mobile.
- Desktop workbench: 256px queue / flexible evidence spine / 344px decision rail.
- Tablet workbench: deal switcher moves into header; 500px evidence spine / 268px decision rail at 768px.
- Mobile workbench: one scroll column plus a 68px decision dock; all primary content uses 16px inline gutters.
- Row minimum: 64px desktop/tablet; 72px mobile.
- Control target: 44×44px minimum on touch layouts; 32px compact visual control may be used only when its interactive hit area remains 44px.
- Content measure: analysis prose max 66ch; legal excerpt max 78ch; technical IDs may use full available width with `overflow-wrap:anywhere`.

### Named spatial primitives and scroll ownership

| Primitive | Job | Scroll owner |
|---|---|---|
| `WorkbenchShell` | Header + bounded body | Body is bounded by `100dvb`; document does not scroll on desktop/tablet |
| `DealQueue` | Retained deal navigation | Queue list owns vertical scroll |
| `EvidenceSpine` | Ordered evidence and derived outputs | Evidence spine owns vertical scroll |
| `DecisionRail` | Sticky decision, brief, blocker, handoff | Rail owns vertical scroll only if its content exceeds the body |
| `DecisionDock` | Mobile decision status + one action | Fixed to viewport bottom; never contains scrollable content |
| `DisclosureStack` | Inline row expansion | Expands inside the current scroll owner |

Nested scrolling is accepted only for the three named desktop/tablet regions because each has a distinct retained job. Popovers and sheets do not create hidden secondary scroll areas when inline disclosure can work.

## 5. Components and states

### Utility header

- **Structure:** product text label, active deal title, search, notes, exports, alerts, settings/profile.
- **Variants:** desktop; tablet with deal switcher; mobile with condensed deal switcher and overflow menu.
- **States:** default, focus, active, alert-count, offline.
- **Accessibility:** landmark `header`; controls have names; alert count is announced as text.
- **Motion:** none on load. Menu disclosure uses standard panel timing.

### Deal queue row

- **Structure:** ordinal, redacted address, jurisdiction, evidence completeness, retained marker.
- **Variants:** selected, unselected, conditional, planned/not-enabled.
- **States:** default, hover, active, focus-visible, loading, stale, unavailable.
- **Accessibility:** selected state uses `aria-current`; full address is available to assistive technology even when visual truncation is applied.
- **Motion:** selection indicator changes opacity; no positional slide.

### Coverage gate

- **Structure:** county, municipality/jurisdiction, coverage status, short explanation, allowed next action.
- **Variants:** private-beta enabled, municipality-required conditional, planned/not-enabled, unsupported, error.
- **States:** see `STATE_MATRIX.md`.
- **Accessibility:** no color-only status; disabled analysis control references the explanatory message.
- **Motion:** status replacement is announced; no animated badge.

### Evidence ledger row

- **Structure:** ordinal, disclosure control, title/description, value or miniature artifact, semantic status, source/citation/hash.
- **Variants:** compact, expanded excerpt, document, derived output, conflict comparison.
- **States:** idle, resolving, verified, partial, missing, stale, conflict, invalid, not-applicable, blocked, error.
- **Accessibility:** row disclosure is a button with `aria-expanded`; source IDs remain keyboard reachable; row status is part of the accessible name.
- **Motion:** expanded content fades and translates no more than 4px; reduced motion makes the change immediate.

### Constraint ladder

- **Structure:** one line per deterministic constraint with input, formula, unit cap, pass/fail, and governing marker.
- **Variants:** complete, incomplete, multi-governing tie, blocked.
- **States:** verified calculation, provisional calculation, abstained.
- **Accessibility:** governing constraint is written explicitly; formula has text equivalent; no bar-length-only comparison.
- **Motion:** verified-row settle may fade the final governing label in after calculation; no animated bars.

### Document evidence row

- **Structure:** document type, date/version, pages, issuer/uploader, extraction status, hash, linked claims.
- **Variants:** survey, plat, civil/construction set, permit, title/legal description.
- **States:** uploaded, scanning, extracted, verified, superseded, corrupt, unsupported-format, missing.
- **Accessibility:** file name is not the sole description; page count and version are text.
- **Motion:** upload progress may animate transform only; reduced motion uses discrete percentage updates.

### Decision rail

- **Structure:** maximum units, governing constraint, purchase ceiling, evidence completeness, opportunity brief, blocker, handoff, primary action.
- **Variants:** verified, conditional, abstained, not-enabled.
- **States:** values inherit provenance status; rail itself never shows “ready” when any required fact is blocked.
- **Accessibility:** starts with a concise decision sentence; repeated numeric values preserve units; sticky behavior does not change DOM order.
- **Motion:** citation trace highlight only; no decorative entrance.

### Grounded opportunity brief

- **Structure:** one to three claims, each with citation IDs; explicit assumptions; limitations; `supported`, `provisional`, or `abstained`.
- **Variants:** supportable opportunity, conditional opportunity, no supported opportunity.
- **States:** generating, grounded, partially grounded, abstained, error.
- **Accessibility:** citations are adjacent links; “AI-generated” and status are text labels.
- **Motion:** text streams are not used. The complete validated brief appears as a single state change.

### Blocker

- **Structure:** severity, exact missing/conflicting fact, consequence, acceptable evidence, owner, action.
- **Variants:** evidence missing, evidence conflict, coverage not enabled, calculation invalid.
- **States:** open, assigned, waiting, resolved, reopened.
- **Accessibility:** blocker receives focus only when user invoked navigation to it; error announcements do not steal focus.
- **Motion:** no pulse. A resolved blocker fades to the audit log.

### Agent handoff strip

- **Structure:** bounded task, agent/person owner, immutable inputs, expected output, status, last event.
- **Variants:** underwriting, zoning research, document extraction, survey review, human review.
- **States:** draft, queued, running, waiting-for-evidence, requires-review, complete, failed, cancelled.
- **Accessibility:** progress is text; activity updates are polite live-region announcements.
- **Motion:** activity dot does not pulse indefinitely. Running status may use a single 150ms opacity cycle when status changes.

### Provenance disclosure

- **Structure:** artifact ID, issuer/origin, acquired timestamp, effective date, hash algorithm/value, extraction version, linked claims.
- **Variants:** source artifact, derived calculation, LLM analysis.
- **States:** hash-bound, hash-mismatch, superseded, unavailable.
- **Accessibility:** 64-character hashes wrap anywhere and include copy action; copy confirmation is announced.
- **Motion:** inline expansion, not a modal by default.

### Mobile decision dock

- **Structure:** status label, maximum units or abstain, purchase ceiling or unavailable, one primary action.
- **Variants:** verified, conditional, abstained, planned/not-enabled.
- **States:** mirrors decision rail.
- **Accessibility:** never obscures focused content; scroll padding equals dock height plus 16px.
- **Motion:** no auto-hide; remains stable.

## 6. Motion and interaction

| Token | Duration | Easing | Use |
|---|---:|---|---|
| `--motion-micro` | 120ms | ease-out | Press, check, focus affordance |
| `--motion-standard` | 180ms | ease-in-out | Inline disclosure |
| `--motion-emphasis` | 260ms | cubic-bezier(0.16, 1, 0.3, 1) | Citation trace |

Rules:

- Animate only opacity and transform.
- No scroll-triggered spectacle, parallax, card stacking, marquee, or decorative loops.
- **Verified-row settle:** when a calculation becomes verified, the governing label fades from 0.65 to 1.0 opacity; nothing moves more than 2px.
- **Citation trace highlight:** focusing a claim applies the verified wash to cited rows for 260ms and leaves a static left rule while focus remains.
- Loading uses text progress and restrained skeletons; no shimmer for users requesting reduced motion.
- `prefers-reduced-motion: reduce` disables transforms and nonessential fades. State changes remain immediate and fully legible.
- Focus is never animated away, moved automatically, or hidden behind a sticky region.

## 7. Depth and surface

Strategy: **tonal shift plus hairline rules**.

- Canvas, panel, recessed, and raised tokens create depth.
- Default panels do not cast shadows.
- Popovers may use `0 8px 24px rgba(23,33,29,0.12)` plus the default border.
- Selected evidence uses a focus/status rule and wash, not a raised card.
- Functional radius scale: 0px ledger boundaries; 4px compact controls; 6px inputs/buttons; 8px popovers. No excessive pills or 20px dashboard cards.
- Paper grain, if used, stays below 2% opacity and is removed under forced-colors/high-contrast modes.

## 8. Accessibility constraints and accepted debt

### Constraints

- Target WCAG 2.2 AA.
- Contrast floor: 4.5:1 body text, 3:1 large text and UI boundaries, 3:1 focus indicator against adjacent colors.
- Full keyboard reachability; logical reading order is header → deal context → evidence spine → decision details → dock action.
- Visible `:focus-visible` uses a 2px focus ring plus 2px offset and never relies on color fill alone.
- Touch targets are at least 44×44px.
- Status changes use polite announcements; blocking errors use assertive announcements only when the user initiated the operation.
- Screen-reader labels expose full redacted parcel IDs, state, and units.
- `prefers-reduced-motion`, forced colors, 200% zoom, and reflow at 320 CSS px must preserve the complete decision path.
- Primary content never requires horizontal scrolling. Wide comparison tables become labeled definition lists or stacked rows.
- Legal and AI caveats use the same readable body scale as other secondary text; never microtype.
- The design does not claim that a verified artifact is a verified entitlement.

### Accepted design debt

| Item | Location | Why accepted | Exit |
|---|---|---|---|
| Built-in ImageGen raster renders at 1586×992 rather than the requested 1440×900 | `reference-direction-a-v4.png` | The built-in output is provenance-bound and retains the correct 16:10 composition, but raster geometry remains non-authoritative | Implementation follows the written responsive geometry and machine truth contract |
| Static design artifacts cannot prove runtime keyboard order, screen-reader output, or motion timing | Entire package | This lane contains no UI implementation | Implementation must run browser-based visual QA and accessibility checks before shipping |
| Exact legal values in the South Florida fixture are illustrative | `CONTENT_FIXTURES_AND_GROUNDING.md` | The artifact demonstrates content shape, not a legal result | Replace fixtures with policy-verified test records before production acceptance |
