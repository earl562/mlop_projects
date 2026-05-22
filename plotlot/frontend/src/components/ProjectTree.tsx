"use client";

import { useState, useMemo, useCallback } from "react";
import type { Project, Site } from "@/lib/workspace";
import type { ChatSession } from "@/lib/sessions";
import { assignSessionToProject, deleteSite } from "@/lib/workspace";

interface ProjectTreeProps {
  workspaceId: string | null;
  projects: Project[];
  sites: Site[];
  sessions: ChatSession[];
  activeSessionId: string | null;
  search: string;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewProject: () => void;
  onRefreshSites: () => void;
}

/* ── Tiny icons ────────────────────────────────────────────────────────── */

function PinIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
      <circle cx="12" cy="9" r="2.5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`flex-shrink-0 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
      aria-hidden="true"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function AssignIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

/* ── Session row — shared between project sites and unsorted list ───────── */

interface SessionRowProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  assignMenu?: React.ReactNode;
}

function SessionRow({ session, isActive, onSelect, onDelete, assignMenu }: SessionRowProps) {
  const title =
    session.title && session.title.trim().length > 0
      ? session.title.length > 38
        ? session.title.slice(0, 38) + "…"
        : session.title
      : "New analysis";

  return (
    <div className="group relative flex items-center">
      <button
        type="button"
        onClick={onSelect}
        className={`flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
          isActive ? "bg-amber-50 dark:bg-amber-900/20" : "hover:bg-stone-100 dark:hover:bg-stone-800"
        }`}
      >
        <span
          className="flex-shrink-0"
          style={{ color: isActive ? "var(--brand)" : "var(--text-muted)" }}
        >
          <PinIcon />
        </span>
        <span
          className="min-w-0 flex-1 truncate"
          style={{ color: isActive ? "var(--brand)" : "var(--text-secondary)" }}
        >
          {title}
        </span>
      </button>

      {/* Action buttons — visible on group hover */}
      <div className="absolute right-1 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        {assignMenu}
        <button
          type="button"
          aria-label={`Delete: ${session.title}`}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--bg-inset)]"
          style={{ color: "var(--text-muted)" }}
        >
          <TrashIcon />
        </button>
      </div>
    </div>
  );
}

/* ── Assign popover for unsorted sessions ──────────────────────────────── */

interface AssignPopoverProps {
  session: ChatSession;
  projects: Project[];
  onAssign: (projectId: string) => void;
}

function AssignPopover({ session, projects, onAssign }: AssignPopoverProps) {
  const [open, setOpen] = useState(false);

  const assignable = projects.filter((p) => p.name !== "Unsorted");
  if (assignable.length === 0) return null;

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Assign to project"
        title="Assign to project"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((p) => !p);
        }}
        className="flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--bg-inset)]"
        style={{ color: "var(--text-muted)" }}
      >
        <AssignIcon />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-30"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            className="absolute right-0 top-full z-40 mt-1 min-w-[160px] overflow-hidden rounded-xl border shadow-[var(--shadow-elevated)]"
            style={{
              background: "var(--bg-surface)",
              borderColor: "var(--border-soft)",
            }}
          >
            <p
              className="px-3 pt-2 pb-1 text-[10px] font-medium uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              Move to project
            </p>
            {assignable.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onAssign(project.id);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--bg-inset)]"
                style={{ color: "var(--text-secondary)" }}
              >
                <FolderIcon />
                <span className="truncate">{project.name}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────────────────── */

export default function ProjectTree({
  workspaceId,
  projects,
  sites,
  sessions,
  activeSessionId,
  search,
  onSelectSession,
  onDeleteSession,
  onNewProject,
  onRefreshSites,
}: ProjectTreeProps) {
  // Default first project expanded
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    const firstId = projects[0]?.id;
    return firstId ? new Set([firstId]) : new Set();
  });

  const toggleExpanded = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Build a sessionId → session map for O(1) lookups
  const sessionMap = useMemo(() => {
    const map = new Map<string, ChatSession>();
    for (const s of sessions) map.set(s.id, s);
    return map;
  }, [sessions]);

  // Build a sessionId → site map for project lookups
  const siteBySession = useMemo(() => {
    const map = new Map<string, Site>();
    for (const s of sites) map.set(s.sessionId, s);
    return map;
  }, [sites]);

  // Sessions that have no site record in this workspace
  const unsortedSessions = useMemo(() => {
    return sessions.filter((s) => !siteBySession.has(s.id));
  }, [sessions, siteBySession]);

  // Filter projects to current workspace
  const workspaceProjects = useMemo(() => {
    if (!workspaceId) return projects;
    return projects.filter((p) => p.workspaceId === workspaceId);
  }, [projects, workspaceId]);

  // Search filter — applied to session titles
  const searchLower = search.trim().toLowerCase();

  const matchesSearch = useCallback(
    (session: ChatSession) => {
      if (!searchLower) return true;
      return session.title.toLowerCase().includes(searchLower);
    },
    [searchLower],
  );

  const handleAssignToProject = useCallback(
    (session: ChatSession, projectId: string) => {
      assignSessionToProject(session.id, projectId, session.title);
      onRefreshSites();
    },
    [onRefreshSites],
  );

  const handleDeleteSiteAndSession = useCallback(
    (sessionId: string) => {
      // Remove the site record if one exists
      const site = siteBySession.get(sessionId);
      if (site) deleteSite(site.id);
      // Remove the underlying session (same as before)
      onDeleteSession(sessionId);
      onRefreshSites();
    },
    [siteBySession, onDeleteSession, onRefreshSites],
  );

  // Empty state — no projects
  if (workspaceProjects.length === 0 && unsortedSessions.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 px-4 py-10">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-full"
          style={{ background: "var(--bg-inset)" }}
        >
          <FolderIcon />
        </div>
        <p className="text-center text-xs" style={{ color: "var(--text-muted)" }}>
          No projects yet. Create one to organize your analyses.
        </p>
        <button
          type="button"
          onClick={onNewProject}
          className="rounded-full px-4 py-2 text-xs font-medium text-white"
          style={{ background: "var(--brand-strong)" }}
        >
          New Project
        </button>
      </div>
    );
  }

  return (
    <nav className="flex flex-col gap-1 py-2" aria-label="Projects">
      {/* ── Projects ────────────────────────────────────────────────────── */}
      {workspaceProjects.map((project) => {
        const projectSites = sites.filter((s) => s.projectId === project.id);

        // Resolve sessions for each site, skip orphans
        const projectSessions = projectSites
          .map((s) => ({ site: s, session: sessionMap.get(s.sessionId) }))
          .filter((x): x is { site: Site; session: ChatSession } => x.session !== undefined)
          .filter(({ session }) => matchesSearch(session));

        // Hide project when search is active and no sessions match
        if (searchLower && projectSessions.length === 0) return null;

        const isExpanded = expandedIds.has(project.id);
        const siteCount = projectSessions.length;

        return (
          <div key={project.id}>
            {/* Project header */}
            <button
              type="button"
              onClick={() => toggleExpanded(project.id)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-inset)]"
            >
              <ChevronIcon expanded={isExpanded} />
              <span
                className="flex-shrink-0"
                style={{ color: "var(--text-muted)" }}
              >
                <FolderIcon />
              </span>
              <span
                className="min-w-0 flex-1 truncate text-xs font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                {project.name}
              </span>
              {siteCount > 0 && (
                <span
                  className="flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                  style={{
                    background: "var(--bg-inset)",
                    color: "var(--text-muted)",
                  }}
                >
                  {siteCount}
                </span>
              )}
            </button>

            {/* Project sessions */}
            {isExpanded && (
              <div className="ml-5 mt-0.5 flex flex-col gap-0.5 border-l pl-2" style={{ borderColor: "var(--border-soft)" }}>
                {projectSessions.length === 0 ? (
                  <p
                    className="px-2 py-2 text-xs"
                    style={{ color: "var(--text-muted)" }}
                  >
                    No analyses yet
                  </p>
                ) : (
                  projectSessions.map(({ site, session }) => (
                    <SessionRow
                      key={site.id}
                      session={session}
                      isActive={session.id === activeSessionId}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => handleDeleteSiteAndSession(session.id)}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* ── Unsorted sessions ───────────────────────────────────────────── */}
      {(() => {
        const filtered = unsortedSessions.filter(matchesSearch);
        if (filtered.length === 0) return null;
        return (
          <div>
            <p
              className="mb-1 px-2 pt-2 text-[11px] font-medium uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              Unassigned
            </p>
            <div className="flex flex-col gap-0.5">
              {filtered.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  isActive={session.id === activeSessionId}
                  onSelect={() => onSelectSession(session.id)}
                  onDelete={() => onDeleteSession(session.id)}
                  assignMenu={
                    workspaceProjects.filter((p) => p.name !== "Unsorted").length > 0 ? (
                      <AssignPopover
                        session={session}
                        projects={workspaceProjects}
                        onAssign={(projectId) =>
                          handleAssignToProject(session, projectId)
                        }
                      />
                    ) : undefined
                  }
                />
              ))}
            </div>
          </div>
        );
      })()}

      {/* ── New project button ───────────────────────────────────────────── */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onNewProject}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors hover:bg-[var(--bg-inset)]"
          style={{ color: "var(--text-muted)" }}
        >
          <svg
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New project
        </button>
      </div>
    </nav>
  );
}
