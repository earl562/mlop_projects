# Build, Test, Debug, Iterate

This is PlotLot's visual implementation loop. A change is complete only when the current
build passes its behavioral assertions and fresh desktop/mobile screenshots have been
reviewed.

## Run the loop

```bash
make btdi
```

Use the connected lane after the database and API are healthy:

```bash
make db-up
make btdi-connected
```

Use `bash scripts/build_test_debug_iterate.sh --headed` when interactive browser
inspection is useful.

Each run writes an ignored timestamped folder under `.artifacts/btdi/` containing:

- production build log;
- Playwright HTML and JSON reports;
- desktop and mobile screenshots;
- trace and video on failure;
- browser console errors, page errors, failed requests, and HTTP 5xx responses;
- `iteration.json` with the run status and artifact paths.

## Agent loop

1. Build and run the smallest journey that reproduces the behavior.
2. Open every screenshot from the current run. Never approve stale captures.
3. Inspect `browser-diagnostics` and the Playwright trace before changing code.
4. State one evidence-backed defect and its likely owning component.
5. Add or tighten the public-behavior assertion that exposes the defect.
6. Make the smallest implementation change that satisfies that assertion.
7. Rerun the affected journey and inspect its fresh screenshots.
8. Run `make btdi`; for connected changes, also run `make btdi-connected`.
9. Stop only when behavior, diagnostics, desktop layout, and mobile layout all pass on
   the same current build.

Do not update screenshot baselines to hide unexplained differences. Do not accept a visual
pass when console errors, failed requests, server errors, clipped content, overlap, or
unreadable mobile layouts remain.
