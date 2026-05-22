/**
 * Workspace → Project → Site storage layer.
 *
 * Sits cleanly above the existing ChatSession layer. ChatSession is unchanged.
 * Sites reference sessions by ID; orphaned references are silently skipped.
 * SSR-safe: all localStorage access is guarded with typeof window checks.
 */

import { listSessions } from "./sessions";

// ---------------------------------------------------------------------------
// Storage keys — never collide with existing "plotlot_sessions" /
// "plotlot_backend_session" / "plotlot_last_session" keys.
// ---------------------------------------------------------------------------

const WORKSPACES_KEY = "plotlot_workspaces";
const PROJECTS_KEY = "plotlot_projects";
const SITES_KEY = "plotlot_sites";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ProjectDealType =
  | "land_deal"
  | "wholesale"
  | "creative_finance"
  | "hybrid"
  | null;

export interface Workspace {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface Project {
  id: string;
  workspaceId: string;
  name: string;
  dealType: ProjectDealType;
  description: string;
  createdAt: string;
  updatedAt: string;
}

export interface Site {
  id: string;
  projectId: string;
  /** References ChatSession.id — may become orphaned after LRU eviction. */
  sessionId: string;
  /** Address label — derived from session title at creation time. */
  address: string;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function uuid(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function readStore<T>(key: string): T[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T[]) : [];
  } catch {
    return [];
  }
}

function writeStore<T>(key: string, data: T[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // localStorage may be full or unavailable — fail silently.
  }
}

// ---------------------------------------------------------------------------
// One-time migration — idempotent, guarded by presence of WORKSPACES_KEY
// ---------------------------------------------------------------------------

/**
 * Called once on sidebar mount. Creates a default "My Workspace" and assigns
 * all existing sessions to an "Unsorted" project. Safe to call repeatedly —
 * the key-presence guard ensures it only runs once per device.
 */
export function runMigrationIfNeeded(): void {
  if (typeof window === "undefined") return;
  if (localStorage.getItem(WORKSPACES_KEY)) return; // already migrated

  const now = new Date().toISOString();
  const workspaceId = uuid();
  const projectId = uuid();

  const defaultWorkspace: Workspace = {
    id: workspaceId,
    name: "My Workspace",
    createdAt: now,
    updatedAt: now,
  };

  const unsortedProject: Project = {
    id: projectId,
    workspaceId,
    name: "Unsorted",
    dealType: null,
    description: "Auto-created from existing conversations.",
    createdAt: now,
    updatedAt: now,
  };

  const sessions = listSessions();
  const sites: Site[] = sessions.map((s) => ({
    id: uuid(),
    projectId,
    sessionId: s.id,
    address: s.title,
    createdAt: s.createdAt,
  }));

  writeStore(WORKSPACES_KEY, [defaultWorkspace]);
  writeStore(PROJECTS_KEY, [unsortedProject]);
  writeStore(SITES_KEY, sites);
}

// ---------------------------------------------------------------------------
// Orphan cleanup — called after sessions-changed or on mount
// ---------------------------------------------------------------------------

/**
 * Removes sites whose sessionId no longer exists in localStorage (evicted by LRU).
 * Returns true if any sites were removed.
 */
export function cleanOrphanedSites(): boolean {
  const sessionIds = new Set(listSessions().map((s) => s.id));
  const all = readStore<Site>(SITES_KEY);
  const clean = all.filter((s) => sessionIds.has(s.sessionId));
  if (clean.length !== all.length) {
    writeStore(SITES_KEY, clean);
    return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Workspace CRUD
// ---------------------------------------------------------------------------

export function listWorkspaces(): Workspace[] {
  return readStore<Workspace>(WORKSPACES_KEY).sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export function createWorkspace(name: string): Workspace {
  const now = new Date().toISOString();
  const workspace: Workspace = { id: uuid(), name, createdAt: now, updatedAt: now };
  const all = readStore<Workspace>(WORKSPACES_KEY);
  all.unshift(workspace);
  writeStore(WORKSPACES_KEY, all);
  return workspace;
}

export function updateWorkspace(id: string, name: string): void {
  const all = readStore<Workspace>(WORKSPACES_KEY);
  const idx = all.findIndex((w) => w.id === id);
  if (idx === -1) return;
  all[idx] = { ...all[idx], name, updatedAt: new Date().toISOString() };
  writeStore(WORKSPACES_KEY, all);
}

// ---------------------------------------------------------------------------
// Project CRUD
// ---------------------------------------------------------------------------

export function listProjects(workspaceId?: string): Project[] {
  const all = readStore<Project>(PROJECTS_KEY);
  const filtered = workspaceId ? all.filter((p) => p.workspaceId === workspaceId) : all;
  return filtered.sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export function createProject(
  workspaceId: string,
  name: string,
  dealType: ProjectDealType,
  description: string,
): Project {
  const now = new Date().toISOString();
  const project: Project = {
    id: uuid(),
    workspaceId,
    name,
    dealType,
    description,
    createdAt: now,
    updatedAt: now,
  };
  const all = readStore<Project>(PROJECTS_KEY);
  all.unshift(project);
  writeStore(PROJECTS_KEY, all);
  return project;
}

export function deleteProject(id: string): void {
  writeStore(
    PROJECTS_KEY,
    readStore<Project>(PROJECTS_KEY).filter((p) => p.id !== id),
  );
  // Cascade: remove all sites in this project
  writeStore(
    SITES_KEY,
    readStore<Site>(SITES_KEY).filter((s) => s.projectId !== id),
  );
}

// ---------------------------------------------------------------------------
// Site CRUD
// ---------------------------------------------------------------------------

export function listAllSites(): Site[] {
  return readStore<Site>(SITES_KEY);
}

export function listSites(projectId: string): Site[] {
  return readStore<Site>(SITES_KEY)
    .filter((s) => s.projectId === projectId)
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function createSite(
  projectId: string,
  sessionId: string,
  address: string,
): Site {
  const now = new Date().toISOString();
  const site: Site = { id: uuid(), projectId, sessionId, address, createdAt: now };
  const all = readStore<Site>(SITES_KEY);
  all.unshift(site);
  writeStore(SITES_KEY, all);
  return site;
}

export function moveSite(siteId: string, newProjectId: string): void {
  const all = readStore<Site>(SITES_KEY);
  const idx = all.findIndex((s) => s.id === siteId);
  if (idx === -1) return;
  all[idx] = { ...all[idx], projectId: newProjectId };
  writeStore(SITES_KEY, all);
}

export function deleteSite(siteId: string): void {
  writeStore(
    SITES_KEY,
    readStore<Site>(SITES_KEY).filter((s) => s.id !== siteId),
  );
}

/**
 * Assign a session to a project. If the session already has a site,
 * move it. Otherwise create a new site record.
 */
export function assignSessionToProject(
  sessionId: string,
  projectId: string,
  address: string,
): void {
  const all = readStore<Site>(SITES_KEY);
  const existing = all.find((s) => s.sessionId === sessionId);
  if (existing) {
    moveSite(existing.id, projectId);
  } else {
    createSite(projectId, sessionId, address);
  }
}

/**
 * Returns the project a session belongs to, or null if unassigned.
 */
export function getSessionProject(sessionId: string): Project | null {
  const site = readStore<Site>(SITES_KEY).find((s) => s.sessionId === sessionId);
  if (!site) return null;
  return readStore<Project>(PROJECTS_KEY).find((p) => p.id === site.projectId) ?? null;
}
