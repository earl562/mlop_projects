# Todo5 evidence index

## Direction packet integrity and selection

- Scenario: validate all three direction packets, the truth-table-correct Direction A v3 reference, and deterministic selection.
- Invocation: `.omo/evidence/todo5-design-selection/verify-todo5.sh`
- Binary observable: exit 0; every manifest row reports `OK`; all three files report PNG RGB 1586×992; recomputed winner is Direction A at 100.0 with no blocker; `TODO5_VERIFICATION: PASS`.
- Artifact: `verification.txt`

## Direction A v3 decision-rail truth correction

- Scenario: correct the rejected v2 rail, which rendered current maximum-units and purchase-ceiling figures while parking was not hash-bound.
- Invocation: exactly one fresh `image_gen.imagegen` call in `ui-mockup` mode using canonical prompt version `direction-a/v1.1.0`.
- Binary observable: prompt SHA-256 `6cc5f6…26a8`; tool-scoped output `call_MsVmzzkbYp4tuStMWeB02Sug.png`; selected project asset `reference-direction-a-v3.png`; output SHA-256 `5594f7…6cf5`; PNG RGB 1586×992; current-correction call count 1.
- Manual observable: the rail visibly shows `MAX UNITS — ABSTAINED / PARKING RULE NOT HASH-BOUND` and `PURCHASE CEILING — ABSTAINED / REQUIRED INPUT MISSING`. No `2` or `$418,000` appears as a current rail result. The evidence ledger, citations/hashes, truthful market gates, and stable-redacted identifiers remain visible.
- Artifacts: `direction-a-v3-truth-correction.json`, `plotlot/artifacts/design/direction-a/imagegen.metadata.json`, and `plotlot/artifacts/design/direction-a/reference-direction-a-v3.png`.

## Non-circular exact commit binding

- Scenario: bind committed evidence to the immutable correction content without claiming a commit contains its own SHA.
- Invocation: create content commit `84d13551b46062075a36ae63e10e5b113483643c`, then commit `CONTENT_COMMIT_BINDING.json`, the verifier, and `content-commit-verification.txt` in its immediate child evidence commit.
- Binary observable: the evidence commit's first parent is the named content commit; content tree is `65deecf7b57196475893c5fa4eb07f25425b20e9`; all 11 changed blob OIDs match; content scope contains no frontend source; full verifier exits 0.
- Artifacts: `CONTENT_COMMIT_BINDING.json` and `content-commit-verification.txt`.

## Desktop, tablet, and mobile current-app baseline

- Scenario: production-build baseline of landing, `/workspace`, explicit Lookup, and explicit Agent states at 1440×900, 768×1024, and 390×844.
- Invocation: Playwright Chromium programmatic capture against `http://127.0.0.1:3215` with `waitUntil: networkidle`, isolated browser contexts, reduced motion, viewport screenshots, `body.ariaSnapshot()`, DOM geometry, console, request-failure, and HTTP error listeners.
- Binary observable: 12 HTTP 200 route captures; 12 non-empty 1:1 viewport PNGs; 12 non-empty ARIA snapshots; 12 state JSON records plus summary; no console errors, no HTTP error responses, and no required workspace request failures. Landing captures record aborted speculative auth-prefetch requests separately.
- Artifacts: `browser-baseline/summary.json`, `browser-baseline/*.png`, `browser-baseline/*.aria.txt`, and `browser-baseline/*.json`.

## Known narrow placeholder implementation gap

- Scenario: reproduce the already-known 375px Lookup placeholder issue without treating it as a selected-design pass.
- Invocation: Playwright Chromium at 375×844 against `/workspace?mode=lookup`.
- Binary observable: input width approximately 126px, `overflow: clip`, full placeholder visibly unavailable, document width remains 375px.
- Artifacts: `browser-baseline/diagnostic-375x844--lookup-placeholder.png` and `browser-baseline/diagnostic-375x844--lookup-placeholder.json`.
- Disposition: implementation gap assigned to Todo21 in `plotlot/artifacts/design/selection/iteration-ledger.json`.

## Browser cleanup

- Scenario: stop the isolated baseline server on port 3215.
- Invocation: interrupt the owned `next start` process, then `curl --max-time 1 http://127.0.0.1:3215/`.
- Binary observable: expected connection failure, curl exit 7.
- Artifact: `server-cleanup.txt`.

## Design-only boundary

No frontend source, release architecture, domain, ByRight, or product behavior was changed. The PNGs are audited composition references only; `plotlot/DESIGN.md` and the selection contract ban raster-backed interactive UI. The historical v2 evidence remains explicitly superseded by the v3 correction and exact two-commit binding above.
