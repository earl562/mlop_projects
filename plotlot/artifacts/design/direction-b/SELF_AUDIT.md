# Direction B Self-Audit

## Design-specific checks

| Check | Result | Evidence |
| --- | --- | --- |
| Dominant model is parcel / APN / folio / record | Pass | `DESIGN.md` interface signature; `ROUTES_FLOW_PANEL_HIERARCHY.md` has no deal/pipeline/chat route |
| Map is an instrument rather than a decorative home screen | Pass | desktop atlas has source date/layers/selection; mobile begins in dossier and exposes a text alternative |
| Source record and replay are first-class | Pass | evidence spine, immutable replay contract, cited `EvidenceClaim` shape |
| Coverage is truthful and bounded | Pass | state matrix names Miami-Dade private beta, municipality-conditional Broward/Palm Beach, planned/not-enabled San Diego |
| Capacity / ceiling abstain when fixture is incomplete | Pass | fixture contains null capacity/ceiling; grounding contract prohibits numeric conclusion |
| LLM is grounded and citation-gated | Pass | structured `GroundedBrief` + five render gates |

## Accessibility audit

| Concern | Requirement / result |
| --- | --- |
| Keyboard map access | map selection has a results-list equivalent; no drag-only workflow |
| Focus | explicit order, visible 3px focus token, drawer focus/restore behavior documented |
| Screen reader semantics | tabs use native button/selected controls; map has selected-parcel textual summary; status includes text |
| Color | verified/warning/status never color-only; required normal-text contrast is at least 4.5:1 |
| Touch | map/evidence/mobile actions preserve 44px minimum targets |
| Zoom/reflow | 200% / 320 CSS px becomes one-column mobile layout; no fixed multi-panel minimum width |
| IDs/data | long canonical IDs wrap at delimiters and retain copy control; identity is never elided into ambiguity |

## Overflow and focus self-audit

- Dossier/evidence internal scroll owners are named and rely on `min-block-size: 0`; desktop page avoids nested uncontrolled scrolling.
- Medium tabs use native horizontal scrolling plus visible controls; mobile sheets replace tight desktop rails.
- Ten-record, long-ID, three-conflict, long-municipality, blank-map, and 200%-zoom cases are defined in the responsive contract.
- Drawer close restores focus to the originating citation; selection confirms before moving focus to dossier identity.
- No tooltip is the sole location for legal identity, coverage, source date, or missing-data reason.

## Motion self-audit

- Motion signals selection/sheet entry only, uses transform/opacity, and is capped at 180ms.
- No decorative flyover, ambient loop, shimmering status, or AI/glow animation exists.
- `prefers-reduced-motion` settles all transitions immediately while preserving focus and state changes.

## Generated reference review

`reference-direction-b-v1.png` was opened after generation and verified as a PNG with 1586×992 RGB dimensions. It supports the intended three-region composition, paper/ink material, APN/folio prominence, source-record rail, coverage badge, and a needs-verification record. It is not treated as copy/fact authority: its invented labels/numbers and its visual suggestion of a broad “Miami-Dade” context are overridden by the written coverage truth.

## Manual document QA

Scenario: a reader opens `README.md`, follows the packet index, and traces the fixture through route, state, calculation, LLM, responsive, and audit contracts.

Invocation: `node -e "JSON.parse(require('fs').readFileSync('artifacts/design/direction-b/fixture-direction-b-v1.json','utf8')); console.log('fixture JSON valid')"` and `shasum -a 256` over the declared packet files.

Observable: valid JSON parses; manifest paths exist and hashes match; fixture retains null `capacity.result` and null `underwriting.purchase_ceiling` while their statuses require verification.

Captured artifacts: `checksums.sha256`, `imagegen.metadata.json`, `DONE_CLAIM.json`.

## Residual implementation debt

This packet does not implement a map engine, source connector, calculator, LLM service, browser UI, or live-data verification. Any future implementation must use the semantic matrix and perform browser visual QA at 1440×900, 768×1024, and 390×844 before claiming UI completion.
