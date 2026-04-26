import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  createSession,
  updateSession,
  getSession,
  deleteSession,
  listSessions,
} from "../../src/lib/sessions";

// Minimal localStorage mock
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value; },
  removeItem: (key: string) => { delete store[key]; },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
};

beforeEach(() => {
  Object.defineProperty(globalThis, "localStorage", { value: localStorageMock, writable: true });
  localStorageMock.clear();
});

afterEach(() => {
  localStorageMock.clear();
});

describe("createSession", () => {
  it("creates a session with required fields", () => {
    const s = createSession("lookup");
    expect(s.id).toBeTruthy();
    expect(s.mode).toBe("lookup");
    expect(s.messages).toHaveLength(0);
    expect(s.title).toBe("New conversation");
  });

  it("evicts oldest session when MAX_SESSIONS (50) reached", () => {
    const sessions = Array.from({ length: 50 }, () => createSession("lookup"));
    const oldest = sessions[0];
    const newest = createSession("lookup");
    expect(getSession(newest.id)).toBeDefined();
    // oldest should be evicted
    expect(getSession(oldest.id)).toBeUndefined();
  });
});

describe("updateSession", () => {
  it("stores backendSessionId correctly", () => {
    const s = createSession("agent");
    const updated = updateSession(s.id, { backendSessionId: "backend-abc-123" });
    expect(updated?.backendSessionId).toBe("backend-abc-123");
    const fetched = getSession(s.id);
    expect(fetched?.backendSessionId).toBe("backend-abc-123");
  });

  it("moves updated session to front", () => {
    const a = createSession("lookup");
    const b = createSession("lookup");
    updateSession(a.id, { title: "Updated A" });
    const list = listSessions();
    expect(list[0].id).toBe(a.id);
    expect(list[1].id).toBe(b.id);
  });

  it("returns undefined for unknown id", () => {
    expect(updateSession("nonexistent", { title: "X" })).toBeUndefined();
  });
});

describe("deleteSession", () => {
  it("removes the session", () => {
    const s = createSession("lookup");
    expect(deleteSession(s.id)).toBe(true);
    expect(getSession(s.id)).toBeUndefined();
  });

  it("returns false for unknown id", () => {
    expect(deleteSession("nonexistent")).toBe(false);
  });
});

describe("listSessions", () => {
  it("returns sessions sorted newest first", () => {
    const a = createSession("lookup");
    const b = createSession("agent");
    // b was created after a, so b should appear first
    const list = listSessions();
    expect(list[0].id).toBe(b.id);
    expect(list[1].id).toBe(a.id);
  });
});
