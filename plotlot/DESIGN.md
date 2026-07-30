# PlotLot Design System

## 1. Atmosphere & Identity

PlotLot should feel like a quiet analyst desk for land-use and acquisition work. The product is not a glossy consumer search tool; it is a workbench for making judgment calls with evidence in view. The signature is warm operational clarity: stone-toned backgrounds, restrained amber emphasis, and dense information blocks that still breathe.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | `--bg-primary` | `#f5f5f6` | `#15110f` | App background |
| Surface/secondary | `--bg-surface` | `#ffffff` | `rgba(29, 24, 21, 0.84)` | Cards and panels |
| Surface/elevated | `--bg-surface-raised` | `#ffffff` | `#211b18` | Raised cards and drawers |
| Surface/inset | `--bg-inset` | `#edeef1` | `#130f0d` | Muted wells and readouts |
| Text/primary | `--text-primary` | `#1c1917` | `#f5f3f0` | Headlines and core body |
| Text/secondary | `--text-secondary` | `#4b5563` | `#c5bbb1` | Support text |
| Text/tertiary | `--text-muted` | `#9ca3af` | `#897d73` | Metadata and hints |
| Border/default | `--border` | `#d7dbe3` | `#3a3028` | Layout boundaries |
| Border/subtle | `--border-soft` | `rgba(125, 95, 66, 0.1)` | `rgba(255, 245, 235, 0.08)` | Soft separators |
| Accent/primary | `--brand` | `#b45309` | `#f59e0b` | CTA, selection, focus |
| Accent/hover | `--brand-hover` | `#92400e` | `#fbbf24` | Hover states |
| Accent/subtle | `--brand-subtle` | `#fffbeb` | `#451a03` | Highlight surfaces |
| Status/success | `--success` | `#047857` | `#34d399` | Successful verification |
| Status/warning | `--warning` | `#d97706` | `#fbbf24` | Preliminary or caution |
| Status/error | `--danger` | `#dc2626` | `#f87171` | Failure and blocking |

### Rules

- Accent color is reserved for action, emphasis, or important state. It is not decorative.
- Panels should rely on tonal hierarchy first, borders second.
- New UI work should use existing CSS variables before introducing new colors.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Display | 32px / 2rem | 700 | 1.15 | 0 | Page hero titles |
| H1 | 24px / 1.5rem | 700 | 1.2 | 0 | Page titles |
| H2 | 20px / 1.25rem | 600 | 1.3 | 0 | Section titles |
| H3 | 16px / 1rem | 600 | 1.4 | 0 | Card headers |
| Body | 14px / 0.875rem | 400 | 1.6 | 0 | Default application text |
| Body/sm | 13px / 0.8125rem | 400 | 1.5 | 0 | Secondary readouts |
| Caption | 12px / 0.75rem | 500 | 1.4 | 0.02em | Labels and metadata |
| Overline | 11px / 0.6875rem | 600 | 1.3 | 0.08em | Uppercase category labels |

### Font Stack

- Primary: `Geist, system-ui, -apple-system, sans-serif`
- Mono: `Geist Mono, SF Mono, Fira Code, monospace`
- Serif: `ui-serif, Georgia, "Times New Roman", serif`

### Rules

- Workspace UI defaults to the sans stack; serif is reserved for display moments and reports.
- Body text does not go below 13px in analyst surfaces.
- Metadata may be uppercase only when used as a compact label, not as paragraph text.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a 4px base.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Tight icon spacing |
| `--space-2` | 8px | Inline groups |
| `--space-3` | 12px | Compact padding |
| `--space-4` | 16px | Default control spacing |
| `--space-5` | 20px | Card internals |
| `--space-6` | 24px | Section spacing |
| `--space-8` | 32px | Major panel spacing |
| `--space-10` | 40px | Large group separation |
| `--space-12` | 48px | Page section rhythm |

### Grid

- Max content width: `1280px`
- Breakpoints: Tailwind defaults with emphasis on `md`, `lg`, and `xl`
- Analyst pages should prefer two-column or three-column information layouts over stacked marketing cards

### Rules

- Workspace sections should read as full-width layouts, not floating card collections.
- Repeated panels use 16px to 24px internal padding.
- Dense analytical data should align on consistent gutters for scanning.

## 5. Components

### Analyst Workbench Panel
- **Structure**: header, short explanatory line, dense content area
- **Variants**: default, success, warning, error
- **Spacing**: 16px to 24px internal padding, 12px vertical content gaps
- **States**: resting, loading, empty
- **Accessibility**: headings use semantic hierarchy; status is visible in text, not color alone
- **Motion**: fade-in only; no decorative movement

### Metric Strip
- **Structure**: compact label, primary value, optional supporting note
- **Variants**: neutral, success, warning
- **Spacing**: 12px inner padding, 8px value-to-label gap
- **States**: default, placeholder
- **Accessibility**: values remain readable at small widths
- **Motion**: none required

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Hover, press, active feedback |
| Standard | 200ms | ease-in-out | Panel reveal, state transitions |
| Emphasis | 320ms | cubic-bezier(0.16, 1, 0.3, 1) | Section entrance |

### Rules

- Animate opacity and transform only.
- Workspace actions must feel responsive, not cinematic.
- Reduced-motion users should get minimal animation without losing state clarity.

## 7. Depth & Surface

### Strategy

Mixed, biased toward tonal shift plus soft borders.

| Level | Value | Usage |
|------|-------|-------|
| Border/default | `1px solid var(--border)` | Primary cards, fields, panels |
| Border/subtle | `1px solid var(--border-soft)` | Quiet subdivisions |
| Shadow/card | `var(--shadow-card)` | Resting elevated cards |
| Shadow/elevated | `var(--shadow-elevated)` | Primary work surfaces and modals |

### Rules

- Use shadows sparingly; most structure should come from background tone and border contrast.
- Panels should feel sturdy and quiet rather than glossy.
