# Todo5 evidence index

## Direction packet integrity and selection

- Scenario: validate all three existing one-call reference packets and deterministic selection.
- Invocation: `.omo/evidence/todo5-design-selection/verify-todo5.sh`
- Binary observable: exit 0; every manifest row reports `OK`; all three files report PNG RGB 1586×992; recomputed winner is Direction A at 100.0 with no blocker; `TODO5_VERIFICATION: PASS`.
- Artifact: `verification.txt`

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

No frontend source, release architecture, domain, ByRight, or product behavior was changed. The PNGs are audited composition references only; `plotlot/DESIGN.md` and the selection contract ban raster-backed interactive UI.
