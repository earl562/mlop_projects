# PlotLot Direction C Design System

## 0. Direction and research record

- Selected direction: **Preconstruction Deal Room / Stage-Gate Binder**. The memorable material is a warm drafting-paper binder: tabbed gates on the left, a current-gate dossier in the center, and accountable handoffs/approvals on the right.
- Distinction contract: no parcel map, operations-command center, dashboard mosaic, chat composer, or file-tree is allowed to become the organizing surface.
- Style reasoning: evidence/review work benefits from a restrained operational UI, not the decorative AIDA/marketing patterns in the gpt-taste guidance. The compatible lessons retained are type discipline, anti-default composition, dense but intentional components, readable headings, and no slop motion.
- Image reference: one built-in `ui-mockup` generation from `../direction-c.prompt.md`; the raster is a visual contract for proportion and material only.
- Design system decision: the packet is image/spec only, so it documents tokens and reusable primitives before implementation. No React/code surface is created here.

### Deterministic gpt-taste record

```text
prompt characters: 3916
seed: 3916 % 97 = 36
hero/layout draw: Editorial split → compatibility override: bounded three-region app shell
component draw: Horizontal accordion, 3D card deck, product panel stack → compatible equivalents: binder tabs, evidence packet stack, handoff rail
motion draw: pinned narrative + text reveal → compatibility override: citation replay focus + status settle
type draw: Cabinet Grotesk → compatibility override: Geist + Geist Mono for technical legibility
```

The overrides are explicit because a cinematic marketing hero, pinning, or decorative motion would undermine the gate binder’s work.

## 1. Identity and atmosphere

Direction C resembles a preconstruction review binder opened on a drafting table: paper layers, hairline dividers, technical type, and a single copper state color that means “someone must decide.” It is quiet but consequential. A line of custody—not a feed—is the signature.

Signature moment: selecting a cited conclusion opens its **evidence replay**, revealing the ordered source artifact, extraction record, formula inputs, and reviewer decision that produced it. It is calm, not theatrical.

## 2. Tokens

### Color

| Role | Token | Value | Use |
|---|---|---:|---|
| Canvas | `--surface-canvas` | `#F5F1E8` | Binder background |
| Paper | `--surface-paper` | `#FCFAF5` | Dossier and rail panels |
| Recessed | `--surface-recessed` | `#ECE6DA` | Gate tabs, inactive packets |
| Raised | `--surface-raised` | `#FFFFFF` | Menus and replay sheet |
| Ink | `--text-primary` | `#222824` | Primary copy |
| Secondary ink | `--text-secondary` | `#657069` | Supporting content |
| Quiet ink | `--text-tertiary` | `#7B827B` | Time and disabled metadata |
| Rule | `--border-default` | `#D8D2C7` | Structural divider |
| Subtle rule | `--border-subtle` | `#E8E2D8` | Interior divider |
| Verified | `--state-verified` | `#315D4B` | Hash-bound/approved evidence—not legal entitlement |
| Verified wash | `--state-verified-wash` | `#E6EEE9` | Supported claim/replay trace |
| Pending | `--state-pending` | `#93612B` | Needs owner/review/municipality confirmation |
| Pending wash | `--state-pending-wash` | `#F4E8D8` | Pending gate and focus context |
| Conflict | `--state-conflict` | `#98483D` | Contradictory/invalid/unsafe evidence |
| Conflict wash | `--state-conflict-wash` | `#F5E2DF` | Conflict detail |
| Informational | `--state-info` | `#305A72` | Source/replay links |
| Focus | `--focus-ring` | `#305A72` | Keyboard focus only |
| Disabled | `--state-disabled` | `#8D948D` | Planned/not-enabled availability |

Rules: status always has text + icon + explanation; no color-only distinctions. Copper never functions as decoration. No gradient text, purple/blue AI glow, glass, luxury gold, or beach palette.

### Type

- UI: `Geist`, `ui-sans-serif`, `system-ui`, sans-serif
- Technical: `Geist Mono`, `ui-monospace`, `SFMono-Regular`, monospace

| Role | Desktop / tablet / mobile | Weight | Leading | Max lines |
|---|---:|---:|---:|---:|
| Binder decision title | 27 / 25 / 23 | 580 | 1.15 | 2 |
| Gate heading | 20 / 19 / 18 | 580 | 1.25 | 2 |
| Dossier section | 16 / 16 / 16 | 560 | 1.3 | 2 |
| Row title | 14 / 14 / 15 | 560 | 1.35 | 2 |
| Body | 14 / 14 / 15 | 400 | 1.5 | unrestricted |
| Label | 11 / 11 / 12 | 580 | 1.35 | 2 |
| Technical | 12 / 12 / 13 | 500 | 1.45 | 2 |
| Major unit/money | 28 / 26 / 24 | 560 mono | 1.1 | 1 |

Legal labels, source hashes, folios, APNs, formulas, units, and money use technical type. Important IDs wrap at any character; they are never ellipsized.

### Space, geometry, depth

Base unit is 4px: `--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 20, `--space-6` 24, `--space-8` 32, `--space-10` 40, `--space-12` 48.

- Header: 56px desktop/tablet; 52px mobile.
- Desktop shell: 248px binder / flexible dossier / 328px handoff rail.
- Tablet: 214px binder / flexible dossier; handoff rail becomes a controlled sheet.
- Mobile: one document column with 68px fixed decision dock; no side-by-side table requirement.
- Functional radii only: 0px rules, 4px tabs, 6px controls, 8px sheets. Panels are separated by tonal shifts + rules, not card shadows.
- Optional replay sheet shadow: `0 10px 28px rgba(34,40,36,0.12)` only.

## 3. Named primitives

| Primitive | Anatomy | States |
|---|---|---|
| `BinderShell` | header + binder spine + dossier + handoff rail | desktop, tablet, mobile |
| `GateTab` | ordinal, title, owner, status, blocker count | default, current, ready, approved, returned, blocked, not-enabled, focus |
| `GateDossier` | decision sentence, exit criterion, required evidence, result, source links | loading, complete, partial, conflict, abstained |
| `EvidencePacket` | title, issuer, date, pages, hash, extraction, linked claims | uploaded, scanning, verified, stale, superseded, corrupt, missing |
| `CapacityWorksheet` | input, source, formula, cap, governing marker | verified, provisional, blocked, abstained |
| `HandoffCard` | sender, recipient, task, immutable inputs, expected output, due state | draft, sent, acknowledged, working, waiting, requires_review, completed, failed |
| `ApprovalLine` | approver, decision, gate revision, time, exception note | pending, approved, returned, exception_accepted |
| `GroundedBrief` | cited claim, qualifier, assumption, limitation | generating, supported, provisional, abstained, error |
| `ReplaySheet` | chronological source → extraction → calculation → claim → approval | open, loading, hash_mismatch, unavailable |
| `DecisionDock` | gate, decision value/abstain, one context action | verified, conditional, blocked, not-enabled |

Primitives used more than once must retain these names and state vocabulary in implementation; no ad-hoc card component substitutes.

## 4. Interaction and information order

The logical order is header → deal identity/coverage → current gate title and exit criterion → current gate evidence → capacity/basis result → blockers → handoff → approval/history. Visual stickiness does not change DOM order.

- Gate select replaces dossier and moves focus to its `h1` only after direct user activation.
- `Request review` is enabled only when the gate is `ready_for_review` and every required evidence packet is hash-bound/current, or an authorized exception is attached.
- `Return to owner` requires a reason and creates a handoff with expected evidence/output.
- `Replay evidence` opens inline on desktop when room permits; otherwise a modal sheet with labelled close control and focus return.
- A claim cannot be clicked into a generic AI conversation. It can be replayed or marked for human review.

## 5. Motion

| Token | Duration | Use |
|---|---:|---|
| `--motion-micro` | 120ms ease-out | focus/press affordance |
| `--motion-standard` | 180ms ease-in-out | disclosure or sheet |
| `--motion-trace` | 240ms cubic-bezier(0.16,1,0.3,1) | evidence replay trace |

Only opacity and transform animate. There is no marquee, parallax, pinned scroll story, decorative spinner, pulsing status dot, or auto-streamed LLM prose. `prefers-reduced-motion: reduce` makes changes immediate while preserving all state information.

## 6. Accessibility constraints

- WCAG 2.2 AA target: body text 4.5:1; large text/UI boundary 3:1; 2px focus ring + 2px offset with 3:1 contrast.
- All gates, source links, replay actions, approval controls, and handoffs are keyboard reachable. Compact visuals retain 44×44px touch hit areas.
- Status is announced in words; gate change and completed handoff use polite live regions. A user-triggered blocking error may be assertive, but focus is not stolen.
- A fixed dock never covers the focus target; mobile scroll padding equals dock height + 16px.
- At 200% zoom and 320px reflow, tables collapse to labelled stacks; no decision-critical horizontal scrolling.
- High contrast/forced colors preserve selected/current/blocked meaning through outline + text, not washes.
- Grounded LLM copy says `AI analysis — supported`, `provisional`, or `abstained`; it never impersonates a reviewer.

## 7. Accepted design debt

| Item | Why | Exit |
|---|---|---|
| Generated raster can contain text inaccuracies | One ImageGen call is mandated; visual raster is non-authoritative | Implementation follows written copy and run-time visual QA |
| Specs cannot prove real keyboard, screen reader, reduced-motion, or approval API behavior | No production UI is built in this packet | Implement and audit all states in a browser before ship |
| Fixture values are illustrative and redacted | This is a design contract, not land-use advice | Replace with policy-verified non-customer test data |
