---
description: Rules for working on the PlotLot Next.js/React frontend
globs: plotlot/frontend/**/*.{ts,tsx,js,jsx,css}
---

# PlotLot Frontend Rules

## Framework & Stack
- Next.js 16 with App Router (not Pages Router). Files go in `src/app/`.
- React 19 — use server components where possible, client components only when needed (`"use client"` directive).
- Tailwind CSS 4 for all styling. No CSS modules, no styled-components, no inline `style={{}}`.
- TypeScript strict mode. Explicit interfaces for all API response shapes.

## Component Patterns
- Components live in `src/components/`. One component per file.
- Name files in PascalCase matching the component name (e.g., `ZoningReport.tsx`).
- Props interfaces go at the top of the file, named `{Component}Props`.
- Use `"use client"` only for components that need browser APIs, state, or effects.
- Prefer composition over prop drilling. Use React context sparingly.

## API Integration (`src/lib/api.ts`)
- All backend calls go through the API client in `src/lib/api.ts`.
- SSE streaming: use the `EventSource` pattern defined in `api.ts`. Don't use `fetch` directly for SSE.
- Backend URL comes from `NEXT_PUBLIC_API_URL` env var.
- Handle loading, error, and empty states for every API call.

## SSE Streaming Pattern
- The `/analyze` endpoint returns SSE events with types: `geocode`, `property`, `zoning`, `analysis`, `calculator`, `heartbeat`, `error`, `done`.
- `AnalysisStream.tsx` is the main streaming component. Follow its pattern for new streaming features.
- Always handle `heartbeat` events (keep connection alive through Render proxy).
- Show progressive disclosure: each pipeline step renders as it arrives.

## Styling Conventions
- Use Tailwind utility classes. Prefer `className` over custom CSS.
- Dark/light mode: use Tailwind's `dark:` variant where needed.
- Responsive: mobile-first with `sm:`, `md:`, `lg:` breakpoints.
- Consistent spacing: use Tailwind's spacing scale (`p-4`, `gap-6`, `mt-8`).
- Card components: `rounded-xl border bg-white shadow-sm dark:bg-gray-900`.

## Key Components
- `AnalysisStream.tsx` — Main SSE streaming UI, pipeline step visualization
- `ZoningReport.tsx` — Full zoning report card with collapsible sections
- `DensityBreakdown.tsx` — 4-constraint visual breakdown (density, lot area, FAR, envelope)
- `SatelliteMap.tsx` — Google Maps satellite view (requires `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`)
- `EnvelopeViewer.tsx` — 3D buildable envelope visualization
- `PropertyCard.tsx` — Property summary with key metrics
- `AddressAutocomplete.tsx` — Address input with Google Places autocomplete
