"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { UserButton } from "@clerk/nextjs";
import { ThemeToggle } from "@/components/ThemeProvider";
import PortfolioPanel from "@/components/PortfolioPanel";
import ProjectTree from "@/components/ProjectTree";
import WorkspaceSelector from "@/components/WorkspaceSelector";
import NewProjectModal from "@/components/NewProjectModal";
import type { ChatSession } from "@/lib/sessions";
import type { SavedAnalysis } from "@/lib/api";
import {
  runMigrationIfNeeded,
  cleanOrphanedSites,
  listWorkspaces,
  createWorkspace,
  listProjects,
  createProject,
  listAllSites,
  type Workspace,
  type Project,
  type Site,
  type ProjectDealType,
} from "@/lib/workspace";

export type { ChatSession };

// ---------------------------------------------------------------------------
// Props — identical to the original interface. SidebarLayout is untouched.
// ---------------------------------------------------------------------------

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onSelectAnalysis?: (analysis: SavedAnalysis) => void;
}

/* ── Sidebar Component ─────────────────────────────────────────────── */
export default function Sidebar({
  sessions,
  activeSessionId,
  isOpen,
  onToggle,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onSelectAnalysis,
}: SidebarProps) {
  const [activeTab, setActiveTab] = useState<"projects" | "portfolio">("projects");
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

  // ── Workspace / Project / Site state (managed internally) ──────────
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);

  // Load workspace data from localStorage
  const loadWorkspaceData = useCallback(() => {
    const wss = listWorkspaces();
    const prjs = listProjects();
    const sts = listAllSites();
    setWorkspaces(wss);
    setProjects(prjs);
    setSites(sts);
    setActiveWorkspaceId((prev) => prev ?? wss[0]?.id ?? null);
  }, []);

  // Mount: migrate once, clean orphans, load data
  useEffect(() => {
    runMigrationIfNeeded();
    cleanOrphanedSites();
    loadWorkspaceData();
  }, [loadWorkspaceData]);

  // Re-sync sites when sessions change (new analysis completed, session deleted)
  useEffect(() => {
    const handler = () => {
      cleanOrphanedSites();
      setSites(listAllSites());
    };
    window.addEventListener("plotlot:sessions-changed", handler);
    return () => window.removeEventListener("plotlot:sessions-changed", handler);
  }, []);

  // ── Keyboard shortcuts ────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "b") {
        e.preventDefault();
        onToggle();
      }
      if (mod && e.key === "n") {
        e.preventDefault();
        onNewChat();
      }
    },
    [onToggle, onNewChat],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // ── Workspace handlers ────────────────────────────────────────────
  const handleSelectWorkspace = useCallback((id: string) => {
    setActiveWorkspaceId(id);
  }, []);

  const handleCreateWorkspace = useCallback(
    (name: string) => {
      const ws = createWorkspace(name);
      loadWorkspaceData();
      setActiveWorkspaceId(ws.id);
    },
    [loadWorkspaceData],
  );

  // ── Project handlers ──────────────────────────────────────────────
  const handleCreateProject = useCallback(
    (name: string, dealType: ProjectDealType, description: string) => {
      if (!activeWorkspaceId) return;
      createProject(activeWorkspaceId, name, dealType, description);
      loadWorkspaceData();
      setShowNewProjectModal(false);
    },
    [activeWorkspaceId, loadWorkspaceData],
  );

  const handleRefreshSites = useCallback(() => {
    setSites(listAllSites());
  }, []);

  /* ── Shared panel content ───────────────────────────────────────── */
  const panelContent = (
    <div className="relative flex h-full flex-col overflow-hidden">
      <div className="pointer-events-none absolute inset-x-4 top-6 h-40 rounded-[2rem] bg-[radial-gradient(circle_at_top,var(--hero-glow-strong),transparent_70%)] opacity-80" />

      {/* Header — PlotLot branding + ThemeToggle */}
      <div className="relative z-10 px-4 pt-6">
        <div className="rounded-[2rem] border border-[var(--border-soft)] bg-[var(--bg-surface)]/92 p-2 shadow-[var(--shadow-panel)] backdrop-blur-xl">
          <div className="rounded-[calc(2rem-0.5rem)] border border-white/50 bg-[var(--bg-surface-raised)] px-4 py-3 dark:border-white/5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--brand-strong)] text-[10px] font-black text-white shadow-[0_10px_30px_rgba(180,83,9,0.2)]">
                  P
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className="font-display text-lg tracking-tight"
                      style={{ color: "var(--text-primary)" }}
                    >
                      PlotLot
                    </span>
                    <span
                      className="rounded-full border border-amber-300/70 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em]"
                      style={{
                        background: "var(--brand-subtle)",
                        color: "var(--brand-strong)",
                      }}
                    >
                      Beta
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] tracking-[0.12em] text-[var(--text-muted)] uppercase">
                    AI zoning analysis
                  </p>
                </div>
              </div>
              <ThemeToggle />
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="rounded-full bg-[var(--bg-primary)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                104 municipalities
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* New analysis button */}
      <div className="relative z-10 px-4 pb-3 pt-4">
        <button
          type="button"
          onClick={onNewChat}
          className="group flex w-full items-center justify-between rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] px-4 py-3 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-card)] transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-0.5 hover:border-[var(--brand-soft-border)]"
        >
          <span>New analysis</span>
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--bg-primary)] text-[var(--text-secondary)] transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-1 group-hover:-translate-y-[1px]">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </span>
        </button>
      </div>

      {/* Data Center nav link */}
      <div className="relative z-10 px-4 pb-2 pt-1">
        <a
          href="/datacenter"
          className="group flex w-full items-center justify-between rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] px-4 py-2.5 text-sm font-medium text-[var(--text-secondary)] shadow-[var(--shadow-card)] transition-colors hover:border-amber-700/40 hover:text-[var(--text-primary)]"
        >
          <span className="flex items-center gap-2">
            <span className="text-base leading-none" aria-hidden>🏭</span>
            Data Center Sites
          </span>
          <span className="rounded-full border border-amber-700/30 bg-amber-700/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-600 dark:text-amber-500">
            New
          </span>
        </a>
      </div>

      {/* Tab switcher */}
      <div className="relative z-10 px-4 pb-2">
        <div className="flex rounded-full border border-[var(--border-soft)] bg-[var(--bg-inset)] p-0.5">
          {(["projects", "portfolio"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`flex-1 rounded-full py-1.5 text-xs font-medium capitalize transition-all ${
                activeTab === tab
                  ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Workspace selector + search — only on projects tab */}
      {activeTab === "projects" && (
        <div className="relative z-10 px-4 pb-3">
          {/* Workspace selector */}
          {workspaces.length > 0 && (
            <div className="mb-2">
              <WorkspaceSelector
                workspaces={workspaces}
                activeWorkspaceId={activeWorkspaceId}
                onSelect={handleSelectWorkspace}
                onCreate={handleCreateWorkspace}
              />
            </div>
          )}
          {/* Search */}
          <input
            ref={searchRef}
            type="text"
            placeholder="Search analyses…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] px-4 py-2.5 text-sm outline-none transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] focus:border-[var(--brand-soft-border)] focus:shadow-[var(--shadow-card)]"
            style={{ color: "var(--text-primary)" }}
          />
        </div>
      )}

      {/* Content — scrollable */}
      <div className="relative z-10 flex-1 overflow-y-auto px-3">
        {activeTab === "projects" ? (
          <ProjectTree
            workspaceId={activeWorkspaceId}
            projects={projects}
            sites={sites}
            sessions={sessions}
            activeSessionId={activeSessionId}
            search={search}
            onSelectSession={onSelectSession}
            onDeleteSession={onDeleteSession}
            onNewProject={() => setShowNewProjectModal(true)}
            onRefreshSites={handleRefreshSites}
          />
        ) : (
          <PortfolioPanel onSelectAnalysis={onSelectAnalysis} />
        )}
      </div>

      {/* Footer — user account + plan link */}
      <div className="relative z-10 border-t border-[var(--border-soft)] px-4 py-4">
        <div className="flex items-center justify-between">
          {clerkEnabled ? (
            <UserButton
              appearance={{
                elements: {
                  avatarBox: "w-7 h-7",
                },
              }}
            />
          ) : (
            <div
              className="flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-semibold"
              style={{ background: "var(--bg-inset)", color: "var(--text-muted)" }}
              aria-label="Guest mode"
              title="Guest mode"
            >
              G
            </div>
          )}
          <div className="flex items-center gap-2">
            <a
              href="/billing"
              className="rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors hover:opacity-80"
              style={{ background: "var(--bg-inset)", color: "var(--text-muted)" }}
            >
              Free
            </a>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              104 municipalities
            </span>
          </div>
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProjectModal && (
        <NewProjectModal
          onClose={() => setShowNewProjectModal(false)}
          onCreate={handleCreateProject}
        />
      )}
    </div>
  );

  return (
    <>
      {/* ── Mobile backdrop ─────────────────────────────────────────── */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar panel ───────────────────────────────────────────── */}
      <aside
        className={`
          fixed top-0 left-0 z-50 h-full w-[320px] border-r transition-transform duration-200
          lg:relative lg:z-auto
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
        style={{
          background: "var(--bg-sidebar)",
          borderColor: "var(--border-soft)",
        }}
      >
        {panelContent}
      </aside>
    </>
  );
}

/* ── SidebarToggle — hamburger button for mobile top bar ───────────── */
export function SidebarToggle({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="Toggle sidebar"
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] transition-colors hover:bg-[var(--bg-surface-raised)]"
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ color: "var(--text-secondary)" }}
      >
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>
  );
}
