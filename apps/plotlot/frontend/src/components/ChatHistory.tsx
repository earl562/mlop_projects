"use client";

import { useMemo, useCallback } from "react";
import type { ChatSession } from "@/lib/sessions";

export type { ChatSession };

/* ── Props ─────────────────────────────────────────────────────────── */
interface ChatHistoryProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

/* ── Date bucket helpers ───────────────────────────────────────────── */
type DateBucket =
  | "Today"
  | "Yesterday"
  | "Previous 7 days"
  | "Previous 30 days"
  | "Older";

const BUCKET_ORDER: DateBucket[] = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Previous 30 days",
  "Older",
];

function getBucket(dateStr: string): DateBucket {
  const now = new Date();
  const date = new Date(dateStr);

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffMs = startOfToday.getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0 || diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays <= 7) return "Previous 7 days";
  if (diffDays <= 30) return "Previous 30 days";
  return "Older";
}

function truncateTitle(title: string, max = 40): string {
  if (!title || title.trim().length === 0) return "New analysis";
  return title.length > max ? title.slice(0, max) + "\u2026" : title;
}

/* ── Trash icon (inline SVG) ───────────────────────────────────────── */
function TrashIcon() {
  return (
    <svg
      width="14"
      height="14"
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
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  );
}

/* ── Component ─────────────────────────────────────────────────────── */
export default function ChatHistory({
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
}: ChatHistoryProps) {
  /* Group sessions into date buckets, sorted by updatedAt desc */
  const grouped = useMemo(() => {
    const sorted = [...sessions].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );

    const map = new Map<DateBucket, ChatSession[]>();
    for (const session of sorted) {
      const bucket = getBucket(session.updatedAt);
      const list = map.get(bucket) ?? [];
      list.push(session);
      map.set(bucket, list);
    }

    return BUCKET_ORDER.filter((b) => map.has(b)).map((bucket) => ({
      label: bucket,
      sessions: map.get(bucket)!,
    }));
  }, [sessions]);

  const handleDelete = useCallback(
    (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      onDelete(id);
    },
    [onDelete]
  );

  /* ── Empty state ──────────────────────────────────────────────────── */
  if (sessions.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 py-12">
        <p
          className="text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          No conversations yet
        </p>
      </div>
    );
  }

  /* ── Session list ─────────────────────────────────────────────────── */
  return (
    <nav className="flex flex-col gap-4 px-2 py-3" aria-label="Chat history">
      {grouped.map(({ label, sessions: bucketSessions }) => (
        <div key={label}>
          {/* Group label */}
          <p
            className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wider"
            style={{ color: "var(--text-muted)" }}
          >
            {label}
          </p>

          {/* Session entries */}
          <ul className="flex flex-col gap-0.5">
            {bucketSessions.map((session) => {
              const isActive = session.id === activeSessionId;

              return (
                <li key={session.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(session.id)}
                    className={`group flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
                      isActive
                        ? "bg-amber-50 dark:bg-amber-900/20"
                        : "hover:bg-stone-100 dark:hover:bg-stone-800"
                    }`}
                  >
                    <span
                      className="min-w-0 truncate"
                      style={{
                        color: isActive
                          ? "var(--brand)"
                          : "var(--text-secondary)",
                      }}
                    >
                      {truncateTitle(session.title)}
                    </span>

                    {/* Delete button — visible on hover */}
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={`Delete conversation: ${session.title}`}
                      onClick={(e) => handleDelete(e, session.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleDelete(
                            e as unknown as React.MouseEvent,
                            session.id
                          );
                        }
                      }}
                      className="flex-shrink-0 cursor-pointer rounded p-0.5 opacity-0 transition-opacity hover:opacity-100 group-hover:opacity-100"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <TrashIcon />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
