"use client";

import { type ComponentType, type SVGProps, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeProvider";
import {
  BarChart3,
  FileText,
  FileSearch,
  LayoutGrid,
  MapPin,
  Menu,
  Network,
  Plus,
} from "lucide-react";
import ChatHistory from "@/components/ChatHistory";
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
}

type NavItem = {
  id: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  mode?: AppMode;
  href?: string;
};

const NAV_ITEMS: NavItem[] = [
  { id: "site-finder", label: "Site Finder", icon: MapPin, mode: "lookup", href: "/workspace" },
  { id: "analyses", label: "Analyses", icon: BarChart3, href: "/analyses" },
  { id: "evidence", label: "Evidence", icon: FileSearch, href: "/evidence" },
  { id: "reports", label: "Reports", icon: FileText, href: "/reports" },
  {
    id: "harness-workspace",
    label: "Harness Workspace",
    icon: LayoutGrid,
    mode: "agent",
    href: "/workspace",
  },
  { id: "connectors", label: "Connectors", icon: Network, href: "/connectors" },
];

function resolveActiveNavId(pathname: string | null, modeParam: string | null): string {
  if (!pathname || pathname === "/workspace") {
    return modeParam === "agent" ? "harness-workspace" : "site-finder";
  }
  const match = NAV_ITEMS.find((item) => item.href === pathname && !item.mode);
  return match ? match.id : "site-finder";
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
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState("");
  const [activeNavId, setActiveNavId] = useState<string>(() => {
    return resolveActiveNavId(pathname, searchParams.get("mode"));
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

  useEffect(() => {
    setActiveNavId(resolveActiveNavId(pathname, searchParams.get("mode")));
  }, [pathname, searchParams]);

  const handleNavClick = useCallback(
    (item: NavItem) => {
      setActiveNavId(item.id);
      if (item.href) {
        const href = item.mode ? `${item.href}?mode=${item.mode}` : item.href;
        router.push(href);
      }
      if (!item.mode) return;
      window.dispatchEvent(
        new CustomEvent("plotlot:mode-change", { detail: { mode: item.mode } }),
      );
      if (window.innerWidth < 1024) setTimeout(onToggle, 0);
    },
    [onToggle, router],
  );

  return (
    <>
      {isOpen && <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onToggle} aria-hidden="true" />}

      <aside
        className={`
          fixed left-0 top-0 z-50 h-full w-[320px] border-r border-[var(--border)] bg-[var(--bg-sidebar)] transition-transform duration-200
          lg:relative lg:z-auto
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
      >
        <div className="flex h-full flex-col overflow-hidden">
          <div className="border-b border-[var(--border-soft)] px-3 pb-3 pt-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--brand-strong)] text-sm font-bold text-white">
                  P
                </div>
                <div className="leading-tight">
                  <p className="font-medium text-[var(--text-primary)]">PlotLot</p>
                  <p className="text-xs tracking-wide text-[var(--text-muted)]">
                    AI ZONING ANALYSIS
                  </p>
                </div>
              </div>
              <ThemeToggle />
            </div>

            <button
              type="button"
              onClick={onNewChat}
              className="flex h-12 w-full items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 text-left text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-inset)]"
            >
                <span className="inline-flex items-center gap-2">
                  <Plus size={16} strokeWidth={2.25} aria-hidden="true" />
                  New analysis
                </span>
                <span className="rounded-md bg-[var(--bg-inset)] px-2 py-1 text-xs font-semibold text-[var(--text-muted)]">
                  ⌘ K
                </span>
            </button>
          </div>

          <div className="border-b border-[var(--border-soft)] px-3 py-3">
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
                          ? "bg-[var(--bg-surface-raised)] text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--bg-inset)]"
                      }`}
                    >
                      <item.icon
                        className="h-5 w-5 text-[var(--text-secondary)]"
                        strokeWidth={2.2}
                        aria-hidden="true"
                      />
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
              className="h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--brand-strong)] focus:ring-2 focus:ring-[var(--brand-subtle)]"
            />
          </div>

          <div className="px-4 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
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

          <div className="border-t border-[var(--border-soft)] px-4 py-3 text-xs text-[var(--text-muted)]">
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
      <Menu size={18} strokeWidth={2} className="text-[var(--text-secondary)]" aria-hidden="true" />
    </button>
  );
}
