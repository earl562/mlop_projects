# Direction C Self-Audit

## Scope and distinction

| Check | Result | Evidence |
|---|---|---|
| Handoffs dominate | pass | Binder spine, `HandoffCard`, `ApprovalLine`, and task flow are primary artifacts |
| Not a map atlas | pass | No map route, map component, or map visual requirement |
| Not an operational command center | pass | Gate dossier and accountable review replace cross-deal KPI/control-room framing |
| Not a generic AI chat/SaaS surface | pass | LLM is cited `GroundedBrief`; no composer/free-form chat route |
| Not a folder-browser deal room | pass | Documents are evidence packets with hashes, page links, and claim lineage |
| No beach/luxury/private-address cues | pass | Redacted fixtures, drafting-paper material, explicit visual avoid list |

## Requirement coverage

| Requirement | Packet location |
|---|---|
| Interface signature / usage | `README.md` |
| Route map, flow, panel hierarchy | `README.md`, `ROUTES_FLOW_PANEL_HIERARCHY.md` |
| Semantic state matrix | `STATE_MATRIX.md` |
| 1440×900 / 768×1024 / 390×844 responsive contract | `RESPONSIVE_WIREFRAMES.md` |
| Miami-Dade private beta; Broward municipality-conditional; San Diego planned/not enabled | `CONTENT_FIXTURES_AND_GROUNDING.md`, `STATE_MATRIX.md` |
| parcel/folio/APN; zoning/setbacks/capacity/max units; constraints; survey/plat; comps; ceiling | `CONTENT_FIXTURES_AND_GROUNDING.md` |
| evidence/replay; approvals/handoffs | `CONTENT_FIXTURES_AND_GROUNDING.md`, `ROUTES_FLOW_PANEL_HIERARCHY.md` |
| grounded LLM + abstention | `CONTENT_FIXTURES_AND_GROUNDING.md`, `STATE_MATRIX.md` |

## Accessibility, focus, and state audit

- Semantic landmarks: header, navigation/binder spine, main dossier, complementary handoff rail, and fixed mobile dock with an accessible label.
- Every status includes a textual state and icon/shape, not color alone. `approved` is always scoped `internal gate decision`.
- Focus: 2px slate focus ring + 2px offset; selected gate uses `aria-current="step"`; dialogs trap and restore focus. Background events never hijack focus.
- Keyboard: gate selection, document replay, handoff acknowledgment, return/approve confirmation, and copy-source controls have a logical route.
- Touch: 44×44px minimum target at tablet/mobile; compact visual controls expand hit area rather than shrinking interaction.
- Contrast: token intent targets WCAG 2.2 AA. Implementation must calculate actual contrast after font/render choice; no white/copper or white/terracotta status text assumption is permitted without verification.
- Zoom/reflow: content preserves all critical information at 200% and 320px. Tables become labelled lists; hashes wrap; no decision depends on horizontal scroll.
- Screen reader: full redacted ID, units, source status, owner, gate status, and disabled reason are exposed. Visual truncation never changes the accessible name.

## Overflow and error audit

- One desktop/tablet scroll owner per retained role: binder tabs, dossier, and overflowed rail. There are no nested packet scrollers.
- Mobile is a single scroll column with bottom dock scroll padding. The dock does not auto-hide or cover focus.
- Long sources/hashes use `overflow-wrap:anywhere`; titles may reach two lines before their metadata moves to a separate row.
- Empty/failed/scanning/corrupt/superseded/missing states specify a recoverable next action. A missing rule produces an abstention, not an empty panel or simulated result.
- Coverage is not silently generalized. Municipality uncertainty and planned coverage remain visible all the way through a disabled analysis/review action.

## Motion audit

- Motion communicates disclosure or evidence lineage only; no dashboard animation, pulsing work indicator, streaming LLM text, parallax, or decorative loops.
- Only opacity/transform may animate, at 120/180/240ms token durations.
- `prefers-reduced-motion` makes nonessential transitions instant while keeping state labels and focus visible.

## Image reference validation plan

This is an image/spec artifact rather than a coded screen, so runtime browser visual QA and independent code-system review are not applicable yet. After the one allowed ImageGen output is copied here, it is validated for PNG signature, dimensions, non-zero bytes, SHA-256 binding to the versioned prompt, and visual compliance with Direction C’s no-map/no-chat/no-luxury constraints. A production UI must subsequently run real browser capture at 390/768/1440, interaction/motion capture, and independent visual-QA reviewers on fresh evidence.
