# Sidebar + Chat History Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible sidebar with persistent chat history to PlotLot's frontend, transforming it from a single-input layout to a two-panel agent interface.

**Architecture:** localStorage-backed session store provides CRUD for chat sessions. A new Sidebar component renders session history grouped by date. The root layout switches from floating nav to sidebar + main flex layout. page.tsx lifts session state and wires CRUD callbacks.

**Tech Stack:** React 19, Next.js 16, Tailwind CSS 4, localStorage, crypto.randomUUID()

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/lib/sessions.ts` | Create | Session CRUD: create, list, get, update, delete, LRU eviction |
| `src/components/ChatHistory.tsx` | Create | Date-grouped session list with active highlight + delete |
| `src/components/Sidebar.tsx` | Create | Collapsible panel: header, search, ChatHistory, settings |
| `src/app/globals.css` | Modify | Add sidebar slide transition + overlay classes |
| `src/app/layout.tsx` | Modify | Replace floating nav with sidebar + main flex layout |
| `src/app/page.tsx` | Modify | Wire session state, CRUD callbacks, auto-save |

---

## Task 1: Session Store (`src/lib/sessions.ts`)

**Files:**
- Create: `frontend/src/lib/sessions.ts`

- [ ] **Step 1: Create session store with types and CRUD**

```typescript
// src/lib/sessions.ts
import { ZoningReportData } from "./api";

const STORAGE_KEY = "plotlot_sessions";
const MAX_SESSIONS = 50;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  report?: ZoningReportData;
  mode: "lookup" | "agent";
  createdAt: string;
  updatedAt: string;
}

function readSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeSessions(sessions: ChatSession[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function createSession(mode: "lookup" | "agent" = "lookup"): ChatSession {
  const now = new Date().toISOString();
  const session: ChatSession = {
    id: crypto.randomUUID(),
    title: "New analysis",
    messages: [],
    mode,
    createdAt: now,
    updatedAt: now,
  };
  const sessions = readSessions();
  sessions.unshift(session);
  // LRU eviction
  if (sessions.length > MAX_SESSIONS) {
    sessions.length = MAX_SESSIONS;
  }
  writeSessions(sessions);
  return session;
}

export function listSessions(): ChatSession[] {
  return readSessions();
}

export function getSession(id: string): ChatSession | undefined {
  return readSessions().find((s) => s.id === id);
}

export function updateSession(id: string, updates: Partial<ChatSession>): void {
  const sessions = readSessions();
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx === -1) return;
  sessions[idx] = { ...sessions[idx], ...updates, updatedAt: new Date().toISOString() };
  // Move to top (most recent)
  const [updated] = sessions.splice(idx, 1);
  sessions.unshift(updated);
  writeSessions(sessions);
}

export function deleteSession(id: string): void {
  const sessions = readSessions().filter((s) => s.id !== id);
  writeSessions(sessions);
}
```

- [ ] **Step 2: Verify file compiles**

Run: `cd frontend && npx tsc --noEmit src/lib/sessions.ts 2>&1 || echo "checked"`

---

## Task 2: ChatHistory Component (`src/components/ChatHistory.tsx`)

**Files:**
- Create: `frontend/src/components/ChatHistory.tsx`

- [ ] **Step 1: Create date-grouped history list**

```tsx
// src/components/ChatHistory.tsx
"use client";

import { ChatSession } from "@/lib/sessions";

interface ChatHistoryProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

function groupByDate(sessions: ChatSession[]): Record<string, ChatSession[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const week = new Date(today.getTime() - 7 * 86400000);
  const month = new Date(today.getTime() - 30 * 86400000);

  const groups: Record<string, ChatSession[]> = {};

  for (const s of sessions) {
    const d = new Date(s.updatedAt);
    let label: string;
    if (d >= today) label = "Today";
    else if (d >= yesterday) label = "Yesterday";
    else if (d >= week) label = "Previous 7 days";
    else if (d >= month) label = "Previous 30 days";
    else label = "Older";

    (groups[label] ||= []).push(s);
  }
  return groups;
}

export default function ChatHistory({ sessions, activeSessionId, onSelect, onDelete }: ChatHistoryProps) {
  const groups = groupByDate(sessions);
  const order = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"];

  if (sessions.length === 0) {
    return (
      <div className="px-3 py-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        No conversations yet
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-2">
      {order.map((label) => {
        const group = groups[label];
        if (!group?.length) return null;
        return (
          <div key={label} className="mb-3">
            <div className="px-2 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              {label}
            </div>
            {group.map((s) => (
              <button
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
                  s.id === activeSessionId
                    ? "bg-amber-50 dark:bg-amber-900/20"
                    : "hover:bg-stone-100 dark:hover:bg-stone-800"
                }`}
                style={{ color: s.id === activeSessionId ? "var(--brand)" : "var(--text-secondary)" }}
              >
                <span className="truncate pr-2">{s.title || "New analysis"}</span>
                <span
                  onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                  className="hidden shrink-0 rounded p-0.5 text-xs opacity-0 transition-opacity hover:bg-stone-200 group-hover:opacity-100 dark:hover:bg-stone-700"
                  style={{ color: "var(--text-muted)" }}
                  role="button"
                  tabIndex={-1}
                  aria-label={`Delete ${s.title}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                </span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

---

## Task 3: Sidebar Component (`src/components/Sidebar.tsx`)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Create collapsible sidebar**

```tsx
// src/components/Sidebar.tsx
"use client";

import { useState, useEffect } from "react";
import { ThemeToggle } from "@/components/ThemeProvider";
import ChatHistory from "@/components/ChatHistory";
import { ChatSession } from "@/lib/sessions";

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  isOpen,
  onToggle,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const [search, setSearch] = useState("");

  // Keyboard shortcut: Cmd/Ctrl + B
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        onToggle();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "n" && !e.shiftKey) {
        e.preventDefault();
        onNewChat();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onToggle, onNewChat]);

  const filtered = search
    ? sessions.filter((s) => s.title.toLowerCase().includes(search.toLowerCase()))
    : sessions;

  return (
    <>
      {/* Mobile overlay backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`fixed left-0 top-0 z-50 flex h-full w-[280px] flex-col border-r transition-transform duration-200 lg:relative lg:z-auto lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{
          background: "var(--bg-surface)",
          borderColor: "var(--border)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-800 text-[11px] font-black text-white dark:bg-amber-600">
              P
            </div>
            <span className="font-display text-lg tracking-tight" style={{ color: "var(--text-primary)" }}>
              PlotLot
            </span>
            <span className="rounded-full px-1.5 py-0.5 text-[10px] font-medium" style={{ background: "var(--brand-subtle)", color: "var(--brand)" }}>
              Beta
            </span>
          </div>
          <ThemeToggle />
        </div>

        {/* New Chat button */}
        <div className="px-3 pt-3">
          <button
            onClick={onNewChat}
            className="flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors hover:bg-stone-100 dark:hover:bg-stone-800"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
            New analysis
          </button>
        </div>

        {/* Search */}
        <div className="px-3 pt-2">
          <input
            type="text"
            placeholder="Search conversations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none transition-colors focus:border-amber-500"
            style={{
              background: "var(--bg-inset)",
              borderColor: "var(--border)",
              color: "var(--text-primary)",
            }}
          />
        </div>

        {/* Session list */}
        <ChatHistory
          sessions={filtered}
          activeSessionId={activeSessionId}
          onSelect={onSelectSession}
          onDelete={onDeleteSession}
        />

        {/* Footer */}
        <div className="border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
          <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            104 municipalities
          </div>
        </div>
      </aside>
    </>
  );
}

/** Hamburger button for mobile — place in layout */
export function SidebarToggle({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-lg p-2 transition-colors hover:bg-stone-100 dark:hover:bg-stone-800 lg:hidden"
      aria-label="Toggle sidebar"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>
  );
}
```

---

## Task 4: Layout + Page Integration

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Update globals.css — add sidebar transition utilities**

Add at end of globals.css:
```css
/* ─── Sidebar ────────────────────────────────────────────────────────── */
.sidebar-open {
  overflow: hidden;
}

@media (min-width: 1024px) {
  .sidebar-open {
    overflow: auto;
  }
}
```

- [ ] **Step 2: Update layout.tsx — replace floating nav with sidebar layout**

Replace the entire `RootLayout` body content (keep metadata, fonts, head script). The new layout uses a `"use client"` wrapper component that manages sidebar state. Since `layout.tsx` must export metadata (server component), create a client wrapper.

Key changes:
- Remove the floating pill nav (`<div className="fixed left-1/2 top-4 z-50">`)
- Remove `<main className="pt-16">`
- Add `SidebarLayout` client component inline that wraps children in flex container with Sidebar
- Mobile: show hamburger toggle in a top bar
- Desktop: sidebar is always present (collapsible)

- [ ] **Step 3: Update page.tsx — wire session state**

Key changes to page.tsx:
- Import session store functions
- Add state: `activeSessionId`, `sessions`
- Load sessions from localStorage on mount
- `handleNewChat()`: create session, set active
- `handleSelectSession(id)`: load session messages + report
- `handleDeleteSession(id)`: delete, switch to next or new
- Auto-save: on messages/report change, debounce updateSession
- Update session title when first address is analyzed
- Pass session props to parent layout via context or URL params

---

## Task 5: Playwright E2E Tests

**Files:**
- Modify: `frontend/tests/hub-integration-regression.spec.ts`

- [ ] **Step 1: Add sidebar E2E tests**

Add tests tagged `@no-db`:
- Sidebar renders on desktop (visible by default at lg breakpoint)
- "New analysis" button creates new session
- Mobile: hamburger toggle shows/hides sidebar
- Theme toggle works from sidebar header

Run: `cd frontend && npx playwright test --grep @no-db`

---

## Execution Order

1. Task 1 (sessions.ts) — no dependencies
2. Task 2 (ChatHistory.tsx) — depends on Task 1
3. Task 3 (Sidebar.tsx) — depends on Tasks 1-2
4. Task 4 (layout + page integration) — depends on Tasks 1-3
5. Task 5 (E2E tests) — depends on Task 4

Tasks 1-3 can be parallelized (2+3 depend on 1's types but not runtime behavior).
