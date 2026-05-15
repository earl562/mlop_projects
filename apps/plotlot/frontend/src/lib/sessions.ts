/**
 * localStorage-backed session store for chat history.
 *
 * SSR-safe: all localStorage access is guarded with typeof window checks.
 * LRU eviction: oldest sessions are removed when MAX_SESSIONS is exceeded.
 */

import type { ZoningReportData } from "./api";

const STORAGE_KEY = "plotlot_sessions";
const MAX_SESSIONS = 50;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  /** Backend session ID — used to resume agent conversations even after backend restarts. */
  backendSessionId?: string;
  createdAt: string;
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a UUID v4 using the crypto API with a Math.random fallback. */
function uuid(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older environments
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Read all sessions from localStorage. Returns [] during SSR. */
function readSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as ChatSession[];
  } catch {
    return [];
  }
}

/** Persist sessions to localStorage. No-op during SSR. */
function writeSessions(sessions: ChatSession[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // localStorage may be full or unavailable — fail silently
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Create a new chat session.
 *
 * If the store already contains MAX_SESSIONS entries the oldest session
 * (by updatedAt) is evicted before inserting the new one.
 */
export function createSession(mode: "lookup" | "agent"): ChatSession {
  const now = new Date().toISOString();
  const session: ChatSession = {
    id: uuid(),
    title: "New conversation",
    messages: [],
    mode,
    createdAt: now,
    updatedAt: now,
  };

  const sessions = readSessions();

  // LRU eviction — remove oldest sessions until we have room
  // Sessions are sorted newest-first, so the tail is the oldest.
  while (sessions.length >= MAX_SESSIONS) {
    sessions.pop();
  }

  // Prepend new session (most recent first)
  sessions.unshift(session);
  writeSessions(sessions);

  return session;
}

/**
 * List all sessions sorted by updatedAt descending (most recent first).
 */
export function listSessions(): ChatSession[] {
  const sessions = readSessions();
  return sessions.sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

/**
 * Get a single session by ID, or undefined if not found.
 */
export function getSession(id: string): ChatSession | undefined {
  const sessions = readSessions();
  return sessions.find((s) => s.id === id);
}

/**
 * Apply a partial update to a session and move it to the top (most recent).
 *
 * Returns the updated session, or undefined if the ID was not found.
 */
export function updateSession(
  id: string,
  updates: Partial<Omit<ChatSession, "id" | "createdAt">>,
): ChatSession | undefined {
  const sessions = readSessions();
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx === -1) return undefined;

  const existing = sessions[idx];
  const updated: ChatSession = {
    ...existing,
    ...updates,
    id: existing.id,
    createdAt: existing.createdAt,
    updatedAt: new Date().toISOString(),
  };

  // Remove from current position and move to the front
  sessions.splice(idx, 1);
  sessions.unshift(updated);
  writeSessions(sessions);

  return updated;
}

/**
 * Delete a session by ID.
 *
 * Returns true if the session was found and removed, false otherwise.
 */
export function deleteSession(id: string): boolean {
  const sessions = readSessions();
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx === -1) return false;

  sessions.splice(idx, 1);
  writeSessions(sessions);

  return true;
}
