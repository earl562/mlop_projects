# Sidebar + Chat History — Design Spec

## Goal

Transform PlotLot from a single-input-bar layout into a two-panel agent interface with collapsible sidebar, persistent chat history, session management, and mode toggle (Lookup vs Agent).

## Current State

- Single-page app with floating pill nav (logo, stats, theme toggle)
- No sidebar, no navigation menu, no chat history persistence
- Chat state lives in React component state — lost on refresh
- Mode toggle exists (Quick Analysis / Chat) but is basic

## Target State

Two-panel layout: collapsible sidebar (left) + main content (right).

### Layout

```
Desktop (≥1024px):
┌────────┬──────────────────────────────────────┐
│Sidebar │  Main Content Area                   │
│ 280px  │  (welcome / conversation / report)   │
│        │                                      │
│NewChat │  Input bar with mode toggle          │
│Search  │  Capability chips                    │
│──────  │                                      │
│Today   │                                      │
│ Sess1  │                                      │
│Yesterd. │                                      │
│ Sess2  │                                      │
│──────  │                                      │
│Settings│                                      │
└────────┴──────────────────────────────────────┘

Mobile (<1024px):
┌──────────────────────────────────────────────┐
│ ☰  PlotLot                        🌙        │
│                                              │
│  Main Content (full width)                   │
│                                              │
│  Input bar                                   │
└──────────────────────────────────────────────┘
Sidebar opens as overlay on hamburger click.
```

### New Components

#### `Sidebar.tsx`
- Width: 280px (desktop), full overlay (mobile)
- Sections: header (logo + new chat), search bar, session list, settings footer
- Collapsible: toggle via hamburger or keyboard shortcut (Cmd+B)
- Transitions: 200ms slide with opacity fade
- Uses existing warm stone + amber design tokens

#### `ChatHistory.tsx`
- Renders date-grouped session list
- Groups: Today, Yesterday, Previous 7 Days, Previous 30 Days, Older
- Each entry shows: first address (truncated to 40 chars) or "New analysis"
- Active session highlighted with amber-50/amber-900 background
- Hover: show delete button (trash icon, right side)
- Click: load session into main content area

#### `ChatSessionStore` (utility in `src/lib/sessions.ts`)
- localStorage-backed CRUD for chat sessions
- Max 50 sessions (LRU eviction on overflow)

### Data Model

```typescript
interface ChatSession {
  id: string;              // uuid
  title: string;           // First address or "New analysis"
  messages: Message[];     // User + assistant messages
  report?: ZoningReportData;
  mode: 'lookup' | 'agent';
  createdAt: string;       // ISO 8601
  updatedAt: string;       // ISO 8601
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}
```

### State Management

- Active session ID stored in React state
- Session list loaded from localStorage on mount
- Auto-save: debounced write to localStorage on message change (500ms)
- Session switching: load messages + report from stored session
- New session: generate UUID, push to session list, clear main area

### Layout Changes to Existing Code

#### `layout.tsx`
- Remove floating pill nav
- Wrap children in flex container: `<Sidebar />` + `<main>`
- Add sidebar state context (open/closed)

#### `page.tsx`
- Lift session state up: messages, report, sessionId
- Add session CRUD callbacks (new, load, delete)
- On address submission: update session title with first address
- On mode change: store in active session

### Responsive Behavior

| Breakpoint | Sidebar | Main Content |
|-----------|---------|-------------|
| `< md` (768) | Hidden, overlay on toggle | Full width |
| `md–lg` (768–1024) | Collapsed icon strip (48px) | Fills remaining |
| `≥ lg` (1024) | Full 280px, collapsible | Shifts right |

### Keyboard Shortcuts

- `Cmd/Ctrl + B` — Toggle sidebar
- `Cmd/Ctrl + K` — Focus search
- `Cmd/Ctrl + N` — New chat

### Design Tokens (reuse existing)

- Sidebar bg: `var(--bg-surface)` (white / dark gray)
- Sidebar border: `var(--border)` (right edge)
- Active item: `bg-amber-50 dark:bg-amber-900/20`
- Hover: `bg-stone-100 dark:bg-stone-800`
- Text: `var(--text-primary)`, `var(--text-secondary)`

### Testing Plan

- Unit: `ChatSessionStore` CRUD (create, read, update, delete, LRU eviction)
- Playwright E2E: sidebar toggle, new chat, session switch, search filter, mobile overlay

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/components/Sidebar.tsx` | Create | Collapsible sidebar with nav + history |
| `src/components/ChatHistory.tsx` | Create | Date-grouped session list |
| `src/lib/sessions.ts` | Create | localStorage session CRUD |
| `src/app/layout.tsx` | Modify | Remove floating nav, add sidebar layout |
| `src/app/page.tsx` | Modify | Lift session state, add CRUD callbacks |
| `src/app/globals.css` | Modify | Add sidebar transition classes |

## Non-Goals (Phase A)

- Mode toggle UI (Phase B)
- Capability chips (Phase B)
- File upload / attachments (Phase C)
- Data source connections (Phase D)
- Server-side session persistence (future, when auth lands)
