# Todo5 evidence index

## Direction packet integrity and selection

- Scenario: validate all three direction packets, the machine-contract-bound Direction A v4 reference, and deterministic selection.
- Invocation: `.omo/evidence/todo5-design-selection/verify-todo5.sh`
- Binary observable: exit 0; every manifest row reports `OK`; all three files report PNG RGB 1586×992; recomputed winner is Direction A at 100.0 with no blocker; `TODO5_VERIFICATION: PASS`.
- Artifact: `verification.txt`

## Direction A v4 privacy and structural-contract correction

- Scenario: replace rejected v3, whose generated queue included address-like copy, and replace prompt-prose assertions with a machine-consumed semantic contract.
- Invocation: exactly one fresh `image_gen.imagegen` call in `ui-mockup` mode using canonical prompt version `direction-a/v1.2.0`; macOS Vision OCR over the copied v4 PNG; structural JSON validation in `verify-todo5.sh`.
- Binary observable: prompt SHA-256 `5a719e…510`; tool-scoped output `call_rvzv9UecapZkYRet64S9f95J.png`; selected asset `reference-direction-a-v4.png`; output SHA-256 `07ea1d…c7b`; truth-contract SHA-256 `c60157…6f3`; PNG RGB 1586×992; current-correction call count 1.
- Visual/OCR observable: only `DEAL-MIA-0420`, `DEAL-MIA-0150`, `DEAL-BRW-0010`, `DEAL-PBC-1234`, and `DEAL-SD-0000` are visible as deal identifiers. No address-like text, folio, APN, owner, phone, email, coordinates, or URL is visible. The rail still shows both outputs as `ABSTAINED`; fixture values appear only in a conditional, not-reliance-ready scenario.
- Structural observable: `design-truth-contract.json` defines versioned state IDs, parking dependencies, `current_value: null`, conditional scenario values, coverage states, ID allowlist, and prohibited data classes. The prompt is hash-bound but never parsed as executable prose.
- Artifacts: `direction-a-v4-privacy-correction.json`, `v4-vision-ocr.txt`, `plotlot/artifacts/design/direction-a/design-truth-contract.json`, `plotlot/artifacts/design/direction-a/imagegen.metadata.json`, and `plotlot/artifacts/design/direction-a/reference-direction-a-v4.png`.

## Non-circular exact commit binding

- Scenario: bind committed evidence to the immutable correction content without claiming a commit contains its own SHA.
- Invocation: create content commit `24c351ab403aa5b55a9874f54f615849d1853eed`, then commit `CONTENT_COMMIT_BINDING.json`, the verifier, OCR, and `content-commit-verification.txt` in its immediate child evidence commit.
- Binary observable: the evidence commit's first parent is the named content commit; content tree is `fc9cde0c2a408f0c8027f4c15a10860a85db7193`; all 13 changed blob OIDs match; content scope contains no frontend source; full verifier exits 0.
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

No frontend source, release architecture, domain, ByRight, or product behavior was changed. The PNGs are audited composition references only; `plotlot/DESIGN.md` and the selection contract ban raster-backed interactive UI. Historical v2/v3 evidence is explicitly superseded by the selected v4 correction and exact two-commit binding above.
