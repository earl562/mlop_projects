# PlotLot Frontend

This directory contains the Next.js frontend for PlotLot.

For the product overview, repo layout, local setup, and workflow contract, start with the root [README.md](/Users/earlperry/Desktop/Projects/EP/README.md).

## Local Development

```bash
cd /Users/earlperry/Desktop/Projects/EP/plotlot/frontend
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Useful Commands

```bash
npm run lint
npm run build
npm run test:ui
npm run test:e2e:no-db
npm run test:e2e:db
npm run test:e2e:visual
```

## Notes

- Playwright outputs belong in ignored local folders or CI artifacts, not git history.
- `Lookup` is the quick-feasibility lane; `Agent` is the deeper workflow lane.
- If you need the product/UX/data contract, see [PLOTLOT_FLOW_CONTRACT.md](/Users/earlperry/Desktop/Projects/EP/plotlot/docs/PLOTLOT_FLOW_CONTRACT.md).
