"use client";

import { useState, useEffect, useCallback } from "react";
import Sidebar, { SidebarToggle } from "@/components/Sidebar";
import {
  listSessions,
  createSession,
  deleteSession,
  type ChatSession,
} from "@/lib/sessions";

export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Auto-hide sidebar on mobile
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const syncFromClient = () => {
      setSidebarOpen(mq.matches);
      const loaded = listSessions();
      setSessions(loaded);
      setActiveSessionId(loaded.length > 0 ? loaded[0].id : null);
    };

    const frame = window.requestAnimationFrame(syncFromClient);

    const handler = (e: MediaQueryListEvent) => {
      setSidebarOpen(e.matches);
    };
    mq.addEventListener("change", handler);
    return () => {
      window.cancelAnimationFrame(frame);
      mq.removeEventListener("change", handler);
    };
  }, []);

  const handleToggle = useCallback(() => setSidebarOpen((p) => !p), []);

  const handleNewChat = useCallback(() => {
    const session = createSession("lookup");
    setSessions(listSessions());
    setActiveSessionId(session.id);
    window.dispatchEvent(new CustomEvent("plotlot:session-selected", { detail: { id: session.id } }));
    setSidebarOpen(false); // close on mobile after action
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setActiveSessionId(id);
    window.dispatchEvent(new CustomEvent("plotlot:session-selected", { detail: { id } }));
    if (window.innerWidth < 1024) setSidebarOpen(false);
  }, []);

  const handleDeleteSession = useCallback(
    (id: string) => {
      deleteSession(id);
      const updated = listSessions();
      setSessions(updated);
      if (activeSessionId === id) {
        setActiveSessionId(updated.length > 0 ? updated[0].id : null);
      }
    },
    [activeSessionId],
  );

  // Expose session refresh for page.tsx via custom event
  useEffect(() => {
    const handler = () => setSessions(listSessions());
    window.addEventListener("plotlot:sessions-changed", handler);
    return () => window.removeEventListener("plotlot:sessions-changed", handler);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)]">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        isOpen={sidebarOpen}
        onToggle={handleToggle}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-[radial-gradient(circle_at_top,var(--hero-glow),transparent_58%)] opacity-80" />
        {/* Mobile top bar */}
        <div
          className="relative z-10 flex items-center border-b border-[var(--border-soft)] bg-[var(--bg-surface)]/90 px-3 py-3 backdrop-blur-xl lg:hidden"
        >
          <SidebarToggle onClick={handleToggle} />
          <div className="ml-2 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--brand-strong)] text-[10px] font-black text-white shadow-[0_10px_30px_rgba(180,83,9,0.18)]">
              P
            </div>
            <span className="font-display text-base tracking-tight text-[var(--text-primary)]">
              PlotLot
            </span>
          </div>
        </div>

        {/* Main content */}
        <main className="relative z-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
