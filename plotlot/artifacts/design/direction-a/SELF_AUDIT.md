# Direction A self-audit

This is a design-artifact audit, not a claim that runtime UI behavior has already been tested. Browser visual QA, accessible-name testing, keyboard traversal, and motion capture remain required before implementation ships.

## Requirement and risk audit

| Check | Result | Evidence / mitigation |
|---|---|---|
| Distinct interface signature | Pass | Continuous numbered evidence ledger plus anchored decision rail, not map-first, file-browser, or chat-first |
| Common acquisition/preconstruction flow | Pass | Route map starts parcel/jurisdiction and ends blocker/handoff/replay |
| Coverage truth | Pass | Miami-Dade private beta; Broward/Palm municipality-required; San Diego County planned/not enabled appear in prompt, fixtures, state matrix, and wireframes |
| Parcel identifiers | Pass | The selected v4 visual uses only the five allowlisted opaque synthetic `DEAL-*` IDs and `PARCEL ID REDACTED`; no address-like text, folio, APN, owner, coordinates, or URL is visible |
| Zoning, setbacks, capacity, max units | Pass | Ordered evidence + cited constraint ladder; the selected v4 rail shows `MAX UNITS — ABSTAINED` because parking is not hash-bound |
| Constraints, survey/plat, documents, comps, ceiling | Pass | Dedicated rows/semantics and source requirements; the selected v4 rail shows `PURCHASE CEILING — ABSTAINED / REQUIRED INPUT MISSING` |
| Evidence/replay | Pass | Artifact schema, hash mismatch quarantine, deterministic replay steps, and run IDs specified |
| Grounded LLM / abstention | Pass | Citation-bound short brief; explicit parking-rule abstention and no streaming speculative copy |
| No screenshot-embedded product | Pass | Reference is a standalone visual-direction artifact; the product is specified as semantic/structural documentation, not an embedded raster implementation |
| No private address | Pass | Selected visual uses opaque synthetic deal IDs only; the textual fixture remains synthetic/redacted and is not rendered as queue copy |

## Accessibility review

- Status always pairs a label, text explanation, and icon; it is never color-only.
- Decision numbers preserve units and conditions in text. The verified green state does not imply legal approval.
- Header, queue, evidence, rail, and dock have a defined keyboard order; citation activation has a return path.
- `:focus-visible` is a 2px focus ring plus offset. The selected row is not the only focus signal.
- Minimum touch target is 44×44px in touch layouts. Compact desktop glyphs retain a larger hit target.
- Expanded rows use `aria-expanded`; citations, hashes, sources, and copy actions are reachable by keyboard.
- Live changes are polite except user-invoked blocking errors; no update steals focus.
- No essential content depends on hover, animation, color perception, or a map.
- At 200% zoom / 320 CSS px, ledger metadata stacks. Long hashes wrap; no primary decision is clipped or requires horizontal scrolling.
- Headings are capped at two lines in normal use; long jurisdiction/legal text moves into a metadata/disclosure pattern rather than forcing a third heading line.

## Overflow and responsive review

| Scenario | Expected handling |
|---|---|
| 1440×900 | Bounded header + 256px queue + flexible evidence spine + 344px rail; named scroll owners only |
| 768×1024 | Queue becomes header switcher; 500px spine + 268px rail; sources stack below values |
| 390×844 | One document scroll column; fixed 68px decision dock with reserved scroll padding |
| 64-char hash / unbroken ID | `overflow-wrap:anywhere`, full accessible label, copy action remains visible |
| Large document version history | Current version first; history moves to inline disclosure/secondary route |
| Long redacted address | Full identity via assistive label and disclosure; visual identity does not obscure folio/APN |
| Blocked capacity | “Unavailable” / “Abstain” replaces misleading numeric continuity; blocker names acceptable evidence |

## Interaction and motion review

- Citation trace has informational purpose: it reveals the evidence supporting a claim.
- Verified-row settle has informational purpose: it confirms the calculation state change.
- Both use transform/opacity only and become immediate under `prefers-reduced-motion: reduce`.
- There is no parallax, marquee, decorative pulse, auto-scrolling, shimmer, or hover-only explanation.
- Button focus, disclosure expansion, and error states remain fully usable without motion.

## Known limitations and implementation gates

1. The selected provenance-bound ImageGen reference is 1586×992 rather than the 1440×900 target and must not be treated as pixel-perfect implementation geometry.
2. Generated raster text is comparison material only; source specifications control exact coverage copy and legal-safety language.
3. This packet intentionally includes no UI code. Before release, implementation must run fresh browser captures at 1440×900, 768×1024, and 390×844; exercise default/focus/expanded/blocker/coverage states; run accessibility checks; and complete visual-QA independent review according to the applicable skill.
