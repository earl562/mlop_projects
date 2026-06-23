# PlotLot Design System

## 1. Atmosphere & Identity

PlotLot is a quiet developer command center: dense, source-backed, and practical without feeling like a generic analytics dashboard. The signature is warm evidence depth: stone surfaces, amber review signals, and PlotLot green action states separate verified facts, assumptions, and next steps without decorative noise.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | `--bg-primary` | `#f5f5f6` | `#15110f` | App background |
| Surface/default | `--bg-surface` | `#ffffff` | `rgba(29, 24, 21, 0.84)` | Panels, reports, chat surfaces |
| Surface/raised | `--bg-surface-raised` | `#ffffff` | `#211b18` | Cards, callouts, nested tool states |
| Surface/inset | `--bg-inset` | `#edeef1` | `#130f0d` | Inputs, skeletons, recessed areas |
| Sidebar | `--bg-sidebar` | `#f2f2f4` | `#181210` | Navigation and workspace rail |
| Text/primary | `--text-primary` | `#1c1917` | `#f5f3f0` | Headings, key values |
| Text/secondary | `--text-secondary` | `#4b5563` | `#c5bbb1` | Body and secondary facts |
| Text/muted | `--text-muted` | `#9ca3af` | `#897d73` | Captions, timestamps, inactive controls |
| Border/default | `--border` | `#d7dbe3` | `#3a3028` | Panel outlines, table rows |
| Border/soft | `--border-soft` | `rgba(125, 95, 66, 0.1)` | `rgba(255, 245, 235, 0.08)` | Subtle separators |
| Border/hover | `--border-hover` | `#c3cad5` | `#5d5047` | Interactive border hover |
| Brand/primary | `--brand` | `#b45309` | `#f59e0b` | Primary CTA, active tabs, focus accents |
| Brand/hover | `--brand-hover` | `#92400e` | `#fbbf24` | CTA hover |
| Brand/strong | `--brand-strong` | `#9a4b0d` | `#f59e0b` | PlotLot badge fills and compact active marks |
| Brand/subtle | `--brand-subtle` | `#fffbeb` | `#451a03` | Warnings and low-risk review panels |
| Brand/muted | `--brand-muted` | `#fef3c7` | `#78350f` | Secondary brand fills |
| Success | `--success` | `#047857` | `#34d399` | Verified, passed, complete |
| Success/subtle | `--success-subtle` | `#ecfdf5` | `#064e3b` | Verified status backgrounds |
| Danger | `--danger` | `#dc2626` | `#f87171` | Failed gates, destructive/error states |
| Danger/subtle | `--danger-subtle` | `#fef2f2` | `#7f1d1d` | Error and blocked-gate backgrounds |
| Warning | `--warning` | `#d97706` | `#fbbf24` | Needs review, partial evidence |
| Warning/subtle | `--warning-subtle` | `#fffbeb` | `#78350f` | Review and pending-state backgrounds |
| Plot/green | `--plot-green` | `#2f6e24` | `#2f6e24` | Public brand mark and agent-ready state |

### Rules

- Official lookup facts use neutral surfaces; warnings use amber; pass/fail gates use success/danger.
- Green is reserved for PlotLot identity, ready/complete states, and primary public-page CTA treatment.
- New colors must be added here before use. Do not introduce purple/blue gradient decoration.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Display | `clamp(44px, 6vw, 76px)` | 850 | 0.95 | 0 | Public hero and agent rail headline |
| H1 | 36px | 750 | 1.12 | 0 | Main workspace titles |
| H2 | 24px-28px | 650 | 1.2 | 0 | Report and section headers |
| H3 | 18px-22px | 650 | 1.25 | 0 | Card titles |
| Body | 16px | 400-500 | 1.6 | 0 | Primary prose |
| Body/sm | 14px | 400-650 | 1.55 | 0 | Dense panels, chat, report rows |
| Caption | 12px | 500-700 | 1.4 | 0 | Metadata and helper text |
| Overline | 10px-11px | 700-800 | 1.3 | 0.08em-0.12em | Stage pills, labels, state tags |

### Font Stack

- Primary: `var(--font-geist-sans), system-ui, -apple-system, sans-serif`
- Mono: `var(--font-geist-mono), "SF Mono", "Fira Code", monospace`
- Display: `var(--font-instrument-serif), Georgia, "Times New Roman", serif`

### Rules

- Use tabular or mono treatment for metrics, counts, IDs, and scores.
- Keep dashboard headings compact; reserve display scale for landing/agent rail contexts.
- Body text never drops below 14px except compact labels in fixed-size controls.

## 4. Spacing & Layout

### Base Unit

All spacing follows a 4px base with an 8-point rhythm for major layout.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Icon-to-label, tight row gaps |
| `--space-2` | 8px | Compact groups |
| `--space-3` | 12px | Form and metric padding |
| `--space-4` | 16px | Standard control/card padding |
| `--space-5` | 20px | Comfortable panel spacing |
| `--space-6` | 24px | Default card padding |
| `--space-8` | 32px | Section group spacing |
| `--space-10` | 40px | Workspace band spacing |
| `--space-12` | 48px | Page section breaks |
| `--space-16` | 64px | Public-page major rhythm |

### Grid

- Max public content width: 1178px from `.coded-container`.
- Workspace shells use two-column grids on desktop and single-column mobile.
- Breakpoints follow Tailwind defaults: `sm 640px`, `md 768px`, `lg 1024px`, `xl 1280px`.

### Rules

- Prefer CSS Grid for dashboard/workbench structure.
- Use `min-height: 100dvh`, not `100vh`, for full-screen surfaces.
- Toolbars, metric tiles, and tabs need stable dimensions so loading states do not shift layout.

## 5. Components

### Evidence Panel
- **Structure**: section heading, repeated source cards, calculator notes, warning/next-step callout.
- **Variants**: populated, empty, warning.
- **Spacing**: `--space-3` within cards, `--space-6` between groups.
- **States**: default, empty, warning.
- **Accessibility**: citations are buttons with source labels; warning icons are decorative unless text is absent.
- **Motion**: fade/translate entry using transform and opacity.

### Report Card
- **Structure**: header with address and badges, tab rail, tab body, source drawer.
- **Variants**: property, zoning, analysis, deal.
- **Spacing**: `--space-5` mobile, `--space-8` desktop.
- **States**: loading, populated, partial coverage, PDF exporting.
- **Accessibility**: tab buttons expose selected state; icon-only controls need labels.
- **Motion**: tab content uses 200-300ms transform/opacity transitions.

### Agent Stage Pill
- **Structure**: inline rounded status label with optional numeric count.
- **Variants**: idle, active, ready, complete, blocked.
- **Spacing**: `--space-2` horizontal padding and 32-38px min height.
- **States**: default, active, complete, blocked.
- **Accessibility**: status must also be expressed in text, not color alone.
- **Motion**: color and border transitions only.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 100-150ms | ease-out | Press feedback and small controls |
| Standard | 180-300ms | ease-in-out | Hover, tab switch, drawer/panel reveal |
| Emphasis | 400-600ms | cubic-bezier(0.16, 1, 0.3, 1) | Public-page reveals and agent workspace transitions |

### Rules

- Animate only `transform`, `opacity`, `filter`, and color/border transitions.
- Every clickable control needs hover, active, and focus-visible states.
- Respect `prefers-reduced-motion` for non-essential transitions.

## 7. Depth & Surface

### Strategy

PlotLot uses a mixed strategy: tonal shifts for hierarchy, thin borders for auditability, and warm shadows only for raised cards or sticky navigation.

| Level | Token | Usage |
|-------|-------|-------|
| Card | `--shadow-card` | Main report card, reusable panels |
| Elevated | `--shadow-elevated` | Modals, popovers, floating menus |
| Navigation | `--shadow-nav` | Sticky public/workbench headers |
| Panel | `--shadow-panel` | Side panels and drawers |

### Rules

- Do not nest cards inside decorative cards; use section spacing or tonal surfaces.
- Borders communicate audit boundaries; shadows communicate elevation.
- Warning/review surfaces must be visually distinct without overwhelming verified data.
