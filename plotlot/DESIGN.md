# PlotLot production design system

Status: authoritative implementation contract
Selected direction: Operational Intelligence Workbench
Decision record: `docs/adr/0019-select-operational-intelligence-workbench.md`

## 0. Authority, purpose, and scope

This document governs PlotLot’s production frontend. Direction packet prose and PNGs are supporting references; this file wins when artifacts differ. Direction A's selected `reference-direction-a-v4.png` is bound to canonical prompt `direction-a/v1.2.0` and exactly one fresh built-in `image_gen.imagegen` call for the opaque-identifier privacy correction in `artifacts/design/direction-a/imagegen.metadata.json`; v1 and rejected v2/v3 are historical only. The selected rail visibly abstains from maximum units and purchase ceiling because parking is not hash-bound, and its visible identifiers are allowlisted opaque synthetic `DEAL-*` IDs only. `artifacts/design/direction-a/design-truth-contract.json` is the machine-consumed semantic source for states, dependencies, scenario separation, coverage, and privacy; prompt prose is not executable. Generated rasters define composition mood only and must never be shipped as interactive UI, background screenshots, image maps, OCR copy sources, or canvas substitutes.

PlotLot helps an acquisition or preconstruction user answer: **what can this parcel support, which evidence supports the answer, what is the purchase ceiling, and what must be resolved before reliance?**

Evidence precedes analysis. Every material conclusion must expose its source, citation, freshness, and provenance state. Unresolved governing facts force a named conditional or abstained state. “Verified” means a displayed evidence artifact passed product provenance checks; it never means legal approval, entitlement, survey certification, or investment advice.

### Coverage truth

- **Miami-Dade:** private beta. Evidence-backed analysis is allowed only when parcel and jurisdiction resolve and required sources pass policy.
- **Broward:** municipality-conditional. Resolve municipality and source coverage before analysis; never imply countywide enablement.
- **Palm Beach:** municipality-conditional under the same rule.
- **San Diego:** planned, not enabled. Context capture or waitlist only; no zoning, capacity, underwriting, or stale-result continuity.
- Unknown jurisdiction is unresolved, not optimistically supported.

No route may claim nationwide analysis or “any property in the US.”

## 1. Product identity

The product feels like a well-organized land-use evidence desk: calm, technical, grounded, and consequential. Its recognizable grammar is:

1. retained deal context;
2. a continuous ordered evidence ledger;
3. an anchored decision summary;
4. exact blocker and bounded handoff;
5. replayable provenance.

It is not a generic SaaS dashboard, AI chat home, CRM pipeline, map hero, folder browser, municipal archive replica, luxury real-estate page, or stage funnel. No beach, palm, resort, ocean, aerial-lifestyle, suburban-house-hero, or gold-luxury clichés.

## 2. Foundation tokens

### Color

| Role | Token | Light value | Rule |
|---|---|---:|---|
| Canvas | `--surface-canvas` | `#F4F1EA` | Primary operational background |
| Panel | `--surface-panel` | `#FBFAF6` | Ledger and decision regions |
| Recessed | `--surface-recessed` | `#ECE9E1` | Filters and closed supporting rows |
| Raised | `--surface-raised` | `#FFFFFF` | Popovers and transient sheets only |
| Primary ink | `--ink-primary` | `#17211D` | Headings and core values |
| Secondary ink | `--ink-secondary` | `#59655F` | Descriptions and labels |
| Quiet ink | `--ink-tertiary` | `#747D78` | Timestamps and disabled explanation |
| Rule | `--rule-default` | `#D3D1C9` | Region and row boundaries |
| Quiet rule | `--rule-subtle` | `#E4E1D9` | Interior separators |
| Verified | `--semantic-verified` | `#285A46` | Provenance-verified evidence |
| Verified wash | `--semantic-verified-wash` | `#E5EEE8` | Cited/selected verified context |
| Conditional | `--semantic-conditional` | `#8A5718` | Missing, conditional, action required |
| Conditional wash | `--semantic-conditional-wash` | `#F5E9D5` | Conditional context |
| Conflict | `--semantic-conflict` | `#943F34` | Conflict, mismatch, invalid result |
| Conflict wash | `--semantic-conflict-wash` | `#F4E2DF` | Conflict context |
| Information | `--semantic-info` | `#536B78` | Source links and neutral information |
| Focus | `--focus-ring` | `#284F73` | Keyboard focus only |
| Disabled | `--semantic-disabled` | `#8C928F` | Planned/not-enabled controls |

Status is never color-only: use icon, explicit label, and explanation. Green never means entitled or approved. Ochre is semantic, never decorative. Brick marks unsafe reliance. Blue-gray is reserved for links, focus, and neutral information.

The operational system is light-first. Dark-theme implementation may not ship until every token has measured WCAG parity and evidence/document legibility is validated across the required matrix.

### Typography

- UI family: `Geist`, `ui-sans-serif`, `system-ui`, sans-serif.
- Technical family: `Geist Mono`, `ui-monospace`, `SFMono-Regular`, monospace.
- Instrument Serif may remain on bounded marketing surfaces. It is prohibited in the workbench, evidence, coverage, decision, handoff, and replay surfaces.

| Role | Desktop / tablet / mobile px | Weight | Line height | Maximum |
|---|---:|---:|---:|---:|
| Decision title | `28 / 26 / 24` | 560 | 1.15 | 2 lines |
| Property title | `24 / 22 / 20` | 580 | 1.2 | 2 lines |
| Section heading | `18 / 18 / 17` | 580 | 1.3 | 2 lines |
| Ledger row title | `15 / 15 / 15` | 560 | 1.35 | 2 lines |
| Body | `14 / 14 / 15` | 400 | 1.5 | natural |
| Compact body | `13 / 13 / 14` | 400 | 1.45 | 3 before disclosure |
| Label | `12 / 12 / 12` | 560 | 1.35 | 2 lines |
| Micro metadata | `11 / 11 / 12` | 450 | 1.4 | 2 lines |
| Technical value | `13 / 13 / 13` mono | 500 | 1.4 | 2 lines |
| Money / units | `30 / 28 / 26` mono | 560 | 1.05 | 1 line |

Folio, APN, ordinance section, citation, hash, timestamp, formula, unit, and money use the technical family. Never clip the only parcel ID, blocker, state, or decision value. Long technical strings use `overflow-wrap:anywhere`.

### Spacing, density, radii, and depth

Base unit: 4px.

| Token | Value |
|---|---:|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |

Operational density is compact but not microtyped. Ledger rows are at least 64px on desktop/tablet and 72px on mobile. Touch targets are at least 44×44px; a visually smaller desktop icon control still provides a 44px touch target when touch input is possible.

Depth comes from tonal steps and hairline rules, not card shadow. Default panels have no shadow. Popovers may use `0 8px 24px rgba(23,33,29,.12)` plus a rule. Radius scale: 0px ledger boundaries, 4px compact controls, 6px inputs/buttons, 8px transient popovers. Avoid pill proliferation, floating cards, glass, glow, gradients, and bento mosaics.

## 3. Route and component anatomy

### Landing

The landing route explains PlotLot’s evidence-led decision sequence and truthful coverage. It may retain restrained marketing composition and Instrument Serif, but it must share product ink, paper, green, rules, and technical evidence motifs. The primary CTA enters a coverage-aware Lookup route. Do not use testimonials, fake partner marks, nationwide availability, vanity KPIs, or a rasterized product screenshot as proof.

### Workspace / retained deals

`WorkbenchShell` contains:

- `UtilityHeader`: product, current deal, search, notes, export, alerts, settings/profile.
- `DealQueue`: retained deals with redacted identity, jurisdiction, evidence completeness, and coverage state.
- `EvidenceSpine`: the primary ordered decision path.
- `DecisionRail`: acquisition result, completeness, blocker, and handoff.
- `DecisionDock`: mobile-only stable summary and one action.

Desktop region scroll owners are bounded and named: queue, evidence spine, and overflowing decision rail. Tablet removes the persistent queue. Mobile has one document scroll owner; hidden desktop regions are inert, non-tabbable, and absent from the accessibility tree.

### Lookup

Lookup is not a chat prompt. Its stages are:

1. input with persistent label and jurisdiction expectation;
2. parcel match and ambiguity resolution;
3. jurisdiction and coverage gate;
4. evidence resolution progress;
5. transition into the same workbench ledger.

The field purpose remains visible at 320–390px; actions reflow instead of compressing the input to placeholder fragments. Placeholder text is supplemental and never the only label.

### Agent

Agent capability lives downstream of evidence. Use `GroundedBrief` for one to three supported, provisional, or abstained claims, each with adjacent citations. Use `AgentHandoff` for a bounded task with immutable inputs, owner, accepted evidence, expected output, status, last event, and reviewer. No open-ended assistant composer is the workspace’s primary home object. Model output appears only after validation; do not stream unvalidated conclusion text.

### Evidence replay

Replay exposes artifact ID, origin/issuer, acquired time, effective date, hash algorithm and value, extraction version, linked claims, supersession, and mismatch status. Full hashes wrap and have an accessible copy action. A hash mismatch quarantines all linked claims.

## 4. Evidence sequence

The canonical ledger order is:

1. Parcel identity.
2. Jurisdiction and coverage.
3. Zoning designation and intent.
4. Setbacks and dimensional rules.
5. Overlays and constraints.
6. Capacity and maximum units.
7. Survey, plat, and construction documents.
8. Comparables.
9. Underwriting and purchase ceiling.
10. Provenance and replay root.

Documents remain evidence objects inside this sequence, not a separate folder-browser mode. A focused map/geometry route may support parcel evidence but never becomes the product home.

`EvidenceRow` anatomy: ordinal; disclosure button; title and purpose; value or miniature semantic artifact; explicit state; source, citation, freshness, and hash. Expansion occurs inline. `aria-expanded` reflects state. Source links remain keyboard reachable.

`ConstraintLadder` shows each deterministic input, formula, unit cap, pass/fail, and governing marker. If a governing input is missing or conflicting, the result is provisional or abstained; do not preserve an attractive numeric value.

`DecisionRail` begins with a concise decision sentence, then maximum units, governing constraint, purchase ceiling, evidence completeness, grounded brief, blocker, handoff, and one primary action. Sticky visual placement must not change DOM order.

## 5. Semantic state contract

### Coverage

| State | Required treatment | Permitted behavior |
|---|---|---|
| `enabled_private_beta` | Miami-Dade private beta + source/freshness caveat | Evidence-backed analysis may continue |
| `municipality_required` | Broward/Palm Beach municipality required | Parcel context only until municipality/source policy passes |
| `planned_not_enabled` | San Diego planned, not enabled | Context/waitlist only |
| `unknown_jurisdiction` | Exact unresolved geography | Resolve; do not infer support |

### Evidence and rules

| State | Treatment | Consequence |
|---|---|---|
| `resolving` | Target source and text progress | Preserve prior value only as explicitly stale |
| `verified` | Icon + Verified + source/citation/hash/freshness | Eligible input when jurisdiction-compatible |
| `partial` | Missing field named | Abstain if governing; otherwise label provisional |
| `missing` | Requested artifact and acceptable source | Create blocker/handoff |
| `stale` | Policy reason and date | Withhold reliance when policy expires |
| `conflict` | Both values/sources and conflict reason | Block dependent conclusion |
| `hash_mismatch` | Expected and observed hash | Quarantine linked claims |
| `cited_but_ambiguous` | Exact ambiguity and review owner | Context only, not a buildable rule |
| `not_hash_bound` | Explicit abstention sentence | Withhold dependent result |

### Derived outputs and handoffs

- `verified_calculation`: formula, inputs, unit cap, citations, and governing marker visible.
- `provisional_calculation`: dependency named; decision rail remains conditional.
- `abstained`: replace dependent numeric result with Unavailable and exact evidence request.
- `grounded`: every claim has adjacent hash-bound citations.
- `partially_grounded`: unsupported portions are omitted and limitation named.
- `handoff_running`: progress as text; no indefinite decorative pulse.
- `handoff_requires_review`: reviewer and blocking evidence visible.
- `complete`, `failed`, `cancelled`: audited terminal event; completion alone does not validate evidence.
- `offline` and `error`: preserve recoverable context, name what is stale/unsaved, provide retry without fabricating continuity.

## 6. Responsive behavior

### Desktop: 1440×900

- Header: 56px.
- Queue: 256px.
- Decision rail: 344px.
- Evidence spine: flexible, minimum 560px.
- Body: `calc(100dvb - 56px)`.
- Switch to tablet composition before squeezing the evidence spine below its minimum.

### Tablet: 768×1024

- Header: 56px with deal switcher.
- Evidence spine: 500px target.
- Decision rail: 268px target.
- Queue becomes a labeled sheet/switcher and is inert while closed.
- Source/citation/hash moves below row title/value before semantic content is truncated.
- At 200% zoom or insufficient spine width, use mobile composition.

### Mobile: 390×844 and narrow reflow

- Header: 52px.
- One sequential column with 16px inline gutters.
- Identity and coverage precede compact decision summary; ledger follows.
- Full rail content appears after evidence and before replay metadata.
- Fixed decision dock: 68px; reserve at least 84px bottom scroll padding.
- Dock never auto-hides, covers focus, or clips status/action.
- Unsupported state says “Analysis unavailable” and offers “View coverage.”
- At 375px and 320px, input label, value, mode/context, and primary action stack or reflow. The 375px placeholder clipping captured in Todo5 is an implementation defect assigned to Todo21, not evidence that this contract passed.

Primary content never requires horizontal scrolling. Wide tables become labeled definition lists or stacked rows. At 200% zoom, reading and focus order remain intact.

## 7. Interaction, focus, and motion

| Token | Duration | Easing | Use |
|---|---:|---|---|
| `--motion-micro` | 120ms | ease-out | Press/check/focus affordance |
| `--motion-standard` | 180ms | ease-in-out | Inline disclosure |
| `--motion-emphasis` | 260ms | cubic-bezier(.16,1,.3,1) | Citation trace |

Only opacity and transform animate. Motion must explain state or relationship:

- citation focus may apply verified wash and a persistent left rule;
- disclosure may fade/translate no more than 4px;
- calculation verification may settle the governing marker no more than 2px;
- upload progress may use transform with text percentage.

No parallax, scroll spectacle, marquee, card stacking, shimmer dependency, decorative loop, or motion on non-interactive content.

`:focus-visible` uses a 2px focus ring plus 2px offset with at least 3:1 adjacent contrast. Focus is not stolen on background updates, moved on status change, or covered by sticky regions. Blocking errors use assertive announcement only after a user-initiated action; ordinary progress is polite.

`prefers-reduced-motion: reduce` disables transforms, decorative fades, shimmer, and auto-scroll. State changes remain immediate and complete.

## 8. Accessibility and content grounding

Target WCAG 2.2 AA:

- body contrast 4.5:1; large text and UI boundaries 3:1;
- full keyboard access and semantic landmarks;
- logical DOM order: header → deal/identity → evidence → decision detail → mobile dock action;
- 44×44px touch targets;
- status text plus icon plus explanation;
- 320px reflow, 200% zoom, forced colors, and reduced motion;
- no color, position, bar length, filename, placeholder, or animation as the sole carrier of meaning;
- caveats use readable body text, never microtype;
- labels expose redacted parcel IDs, units, state, and disabled reason.

Content rules:

- use stable-redacted synthetic identifiers in docs, demos, fixtures, and evidence;
- never include private customer addresses, owner names, lead payloads, credentials, or raw external logs;
- distinguish source fact, deterministic derivation, and grounded model summary;
- every material fact has source ID, citation, effective/acquired time, freshness, and hash state;
- numbers include units and basis;
- claims say supported, provisional, or abstained;
- no legal certainty, automatic approval, guaranteed entitlement, or investment recommendation;
- generated raster text is never a data source.

## 9. Coverage and release readiness

Implementation is not release-ready until every relevant route, state, and viewport in `artifacts/design/selection/acceptance-matrix.json` has fresh artifacts captured after the last source edit:

- same-size screenshot;
- semantic DOM/ARIA capture;
- console errors;
- failed required requests and HTTP error responses;
- keyboard/focus proof;
- reduced-motion proof;
- horizontal overflow measurement;
- real interaction for disclosure, coverage block, replay, and handoff.

Binary blockers:

- nationwide/countywide enabled language;
- unsupported market showing current zoning/capacity/underwriting;
- raster used as interactive UI;
- generic assistant composer as primary workspace;
- missing citation/provenance on a material conclusion;
- clipped or hidden primary input/state/action;
- off-canvas focusable controls;
- unresolved required state or viewport;
- contrast, focus, touch-target, or reflow failure;
- required console/network failure.

The three reference packet PNGs do not constitute a selected-design pass. Todo5 establishes the contract; Todo21 must implement and prove it.

## 10. Token migration map

| Current family | Disposition | Production target |
|---|---|---|
| `--font-geist-sans`, `--font-geist-mono` | **Preserve** | Rename only if needed to UI/technical semantic aliases |
| `--font-instrument-serif` | **Preserve with boundary** | Marketing only; prohibited in operational UI |
| `--plot-bg`, `--plot-surface`, `--plot-text*`, `--plot-border` | **Replace through aliases** | Map to canvas/panel/ink/rule tokens so landing and product share one foundation |
| `--plot-green*` | **Preserve intent, replace values/roles** | Use verified/brand evidence family; green never means approval |
| `--bg-primary`, `--bg-surface*`, `--bg-inset`, `--bg-sidebar` | **Replace** | `--surface-canvas/panel/recessed/raised`; remove route-specific neutral drift |
| `--text-primary`, `--text-secondary`, `--text-muted` | **Replace through aliases** | `--ink-primary/secondary/tertiary` |
| `--brand`, `--brand-hover`, `--brand-strong`, `--brand-subtle`, `--brand-muted` | **Replace** | Split verified, conditional, conflict, information, and action roles; do not use amber as generic brand decoration |
| `--success*`, `--warning*`, `--danger*` | **Replace** | Semantic verified/conditional/conflict families with text/icon/explanation rules |
| `--border`, `--border-soft`, `--border-hover` | **Replace through aliases** | `--rule-default/subtle` plus explicit focus token |
| `--shadow-card`, `--shadow-elevated`, `--shadow-nav`, `--shadow-panel`, `--plot-shadow` | **Deprecate** | Hairline/tonal depth; retain only one popover elevation |
| `--nav-bg`, `--nav-border` | **Replace** | Opaque paper/panel and rule tokens in operational header |
| `--hero-glow*`, `--input-fade-from` | **Deprecate** | No operational glow/fade decoration |
| Dark-family overrides | **Deprecate for production workbench** | Reintroduce only after complete measured parity |
| Large rounded card/pill utilities | **Deprecate as default grammar** | 0/4/6/8px functional radius scale |
| Fade-up/fade-in/pulse utility family | **Replace** | Named state motion tokens; no indefinite pulse |

Migration is semantic, not a global search-and-replace. Components move to aliases by anatomy, and old families are removed only after no runtime consumer remains.
