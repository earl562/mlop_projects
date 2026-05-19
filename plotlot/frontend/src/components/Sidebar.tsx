"use client";

import { useState, useEffect, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeProvider";
import PortfolioPanel from "@/components/PortfolioPanel";
import ProjectTree from "@/components/ProjectTree";
import WorkspaceSelector from "@/components/WorkspaceSelector";
import NewProjectModal from "@/components/NewProjectModal";
import type { ChatSession } from "@/lib/sessions";
import type { AppMode } from "@/components/ModeToggle";

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

type NavItem = {
  id: string;
  label: string;
  icon: string;
  mode?: AppMode;
  href?: string;
};

const NAV_ITEMS: NavItem[] = [
  { id: "site-finder", label: "Site Finder", icon: "⌖", mode: "lookup", href: "/" },
  { id: "analyses", label: "Analyses", icon: "◫", href: "/analyses" },
  { id: "evidence", label: "Evidence", icon: "◉", href: "/evidence" },
  { id: "reports", label: "Reports", icon: "☰", href: "/reports" },
  { id: "harness-workspace", label: "Harness Workspace", icon: "✳", mode: "agent", href: "/" },
  { id: "connectors", label: "Connectors", icon: "◎", href: "/connectors" },
];

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
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState("");
  const [activeNavId, setActiveNavId] = useState<string>(() => {
    if (!pathname || pathname === "/") return "site-finder";
    const match = NAV_ITEMS.find((item) => item.href === pathname);
    return match ? match.id : "site-finder";
  });

  const filtered = search.trim()
    ? sessions.filter((s) => s.title.toLowerCase().includes(search.trim().toLowerCase()))
    : sessions;

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

  useEffect(() => {
    const handler = (event: Event) => {
      const mode = (event as CustomEvent<{ mode: AppMode }>).detail?.mode;
      if (mode === "lookup") setActiveNavId("site-finder");
      if (mode === "agent") setActiveNavId("harness-workspace");
    };
    window.addEventListener("plotlot:mode-changed", handler);
    return () => window.removeEventListener("plotlot:mode-changed", handler);
  }, []);

  const handleNavClick = useCallback(
    (item: NavItem) => {
      setActiveNavId(item.id);
      if (item.href) router.push(item.href);
      if (!item.mode) return;
      window.dispatchEvent(
        new CustomEvent("plotlot:mode-change", { detail: { mode: item.mode } }),
      );
    },
    [router],
  );

  return (
    <>
      {isOpen && <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onToggle} aria-hidden="true" />}

      <aside
        className={`
          fixed left-0 top-0 z-50 h-full w-[320px] border-r transition-transform duration-200
          lg:relative lg:z-auto
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
        style={{
          background: "#f2f2f4",
          borderColor: "#e5e7eb",
        }}
      >
        <div className="flex h-full flex-col overflow-hidden">
          <div className="border-b border-[#e5e7eb] px-3 pb-3 pt-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-black text-sm font-bold text-white">
                  P
                </div>
                <div className="leading-tight">
                  <p className="font-medium text-[#111827]">PlotLot</p>
                  <p className="text-xs tracking-wide text-[#6b7280]">AI ZONING ANALYSIS</p>
                </div>
              </div>
              <ThemeToggle />
            </div>

            <button
              type="button"
              onClick={onNewChat}
              className="flex h-12 w-full items-center justify-between rounded-xl border border-[#d7dbe3] bg-white px-4 text-left text-sm font-medium text-[#111827] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            >
              <span className="inline-flex items-center gap-2">
                <span className="text-base">⊕</span>
                New analysis
              </span>
              <span className="rounded-md bg-[#eef1f5] px-2 py-1 text-xs font-semibold text-[#64748b]">⌘ K</span>
            </button>
          </div>

          <div className="border-b border-[#e5e7eb] px-3 py-3">
            <ul className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const active = item.id === activeNavId;
                return (
                  <li key={item.label}>
                    <button
                      type="button"
                      onClick={() => handleNavClick(item)}
                      aria-current={active ? "page" : undefined}
                      data-testid={`sidebar-nav-${item.id}`}
                      className={`flex h-11 w-full items-center gap-2 rounded-xl px-3 text-left text-sm font-medium transition-colors ${
                        active
                          ? "bg-[#e5e7eb] text-[#111827]"
                          : "text-[#374151] hover:bg-[#eceff3]"
                      }`}
                    >
                      <span className="w-5 text-center text-base leading-none">{item.icon}</span>
                      <span>{item.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="px-3 pb-2 pt-3">
            <input
              type="text"
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-11 w-full rounded-xl border border-[#d7dbe3] bg-white px-3 text-sm text-[#111827] placeholder:text-[#9ca3af] outline-none transition-colors focus:border-[#b7c0cf]"
            />
          </div>

          <div className="px-4 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9ca3af]">
            Chat History
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <ChatHistory
              sessions={filtered}
              activeSessionId={activeSessionId}
              onSelect={onSelectSession}
              onDelete={onDeleteSession}
            />
          </div>

          <div className="border-t border-[#e5e7eb] px-4 py-3 text-xs text-[#6b7280]">
            <div className="flex items-center justify-between">
              <span>104 municipalities</span>
              <span>Free</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

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
