"use client";

import { useState, useRef, useEffect } from "react";
import type { Workspace } from "@/lib/workspace";

interface WorkspaceSelectorProps {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string) => void;
}

export default function WorkspaceSelector({
  workspaces,
  activeWorkspaceId,
  onSelect,
  onCreate,
}: WorkspaceSelectorProps) {
  const [open, setOpen] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);
  const [newName, setNewName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const active = workspaces.find((w) => w.id === activeWorkspaceId);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreatingNew(false);
        setNewName("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus input when creating
  useEffect(() => {
    if (creatingNew) inputRef.current?.focus();
  }, [creatingNew]);

  const handleCreate = () => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    onCreate(trimmed);
    setNewName("");
    setCreatingNew(false);
    setOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleCreate();
    if (e.key === "Escape") {
      setCreatingNew(false);
      setNewName("");
    }
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-inset)]"
      >
        <span
          className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-[9px] font-black text-white"
          style={{ background: "var(--brand-strong)" }}
          aria-hidden="true"
        >
          {(active?.name ?? "W").charAt(0).toUpperCase()}
        </span>
        <span
          className="min-w-0 flex-1 truncate text-xs font-medium"
          style={{ color: "var(--text-secondary)" }}
        >
          {active?.name ?? "My Workspace"}
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`flex-shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          style={{ color: "var(--text-muted)" }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border shadow-[var(--shadow-elevated)]"
          style={{
            background: "var(--bg-surface)",
            borderColor: "var(--border-soft)",
          }}
        >
          {/* Workspace list */}
          {workspaces.map((ws) => (
            <button
              key={ws.id}
              type="button"
              onClick={() => {
                onSelect(ws.id);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--bg-inset)]"
            >
              <span
                className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[9px] font-black text-white"
                style={{ background: "var(--brand-strong)" }}
              >
                {ws.name.charAt(0).toUpperCase()}
              </span>
              <span
                className="min-w-0 flex-1 truncate font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {ws.name}
              </span>
              {ws.id === activeWorkspaceId && (
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ color: "var(--brand)" }}
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          ))}

          {/* Divider */}
          <div className="my-1 border-t" style={{ borderColor: "var(--border-soft)" }} />

          {/* New workspace */}
          {creatingNew ? (
            <div className="px-3 py-2">
              <input
                ref={inputRef}
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Workspace name…"
                className="w-full rounded-lg border bg-transparent px-2 py-1 text-xs outline-none focus:border-[var(--brand-soft-border)]"
                style={{
                  borderColor: "var(--border-soft)",
                  color: "var(--text-primary)",
                }}
              />
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!newName.trim()}
                  className="flex-1 rounded-lg py-1 text-xs font-medium text-white transition-opacity disabled:opacity-40"
                  style={{ background: "var(--brand-strong)" }}
                >
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreatingNew(false);
                    setNewName("");
                  }}
                  className="flex-1 rounded-lg py-1 text-xs font-medium transition-colors hover:bg-[var(--bg-inset)]"
                  style={{ color: "var(--text-muted)" }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setCreatingNew(true)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--bg-inset)]"
              style={{ color: "var(--text-muted)" }}
            >
              <svg
                width="12"
                height="12"
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
              New workspace
            </button>
          )}
        </div>
      )}
    </div>
  );
}
