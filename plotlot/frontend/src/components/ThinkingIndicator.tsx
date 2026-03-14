"use client";

import { useState } from "react";
import type { ThinkingEvent } from "@/lib/api";

interface ThinkingIndicatorProps {
  events: ThinkingEvent[];
}

export default function ThinkingIndicator({ events }: ThinkingIndicatorProps) {
  const [expanded, setExpanded] = useState(false);

  if (events.length === 0) return null;

  const allThoughts = events.flatMap((e) => e.thoughts);

  return (
    <div className="my-2 rounded-lg border border-blue-200 bg-blue-50/50 dark:border-blue-800/50 dark:bg-blue-950/20">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <svg
          className={`h-3.5 w-3.5 text-blue-500 transition-transform ${expanded ? "rotate-90" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
        <svg className="h-3.5 w-3.5 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 2a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2zM10 15a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 15zM10 7a3 3 0 100 6 3 3 0 000-6zM15.657 5.404a.75.75 0 10-1.06-1.06l-1.061 1.06a.75.75 0 001.06 1.06l1.06-1.06zM6.464 14.596a.75.75 0 10-1.06-1.06l-1.06 1.06a.75.75 0 001.06 1.06l1.06-1.06zM18 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 0118 10zM5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5A.75.75 0 015 10zM14.596 15.657a.75.75 0 001.06-1.06l-1.06-1.061a.75.75 0 10-1.06 1.06l1.06 1.06zM5.404 6.464a.75.75 0 001.06-1.06l-1.06-1.06a.75.75 0 10-1.06 1.06l1.06 1.06z" />
        </svg>
        <span className="text-xs font-medium text-blue-700 dark:text-blue-400">
          AI Reasoning ({allThoughts.length} insight{allThoughts.length !== 1 ? "s" : ""})
        </span>
      </button>

      {expanded && (
        <div className="border-t border-blue-200 px-3 py-2 dark:border-blue-800/50">
          <ul className="space-y-1">
            {allThoughts.map((thought, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-blue-700 dark:text-blue-400">
                <span className="mt-0.5 text-blue-400">&#8226;</span>
                {thought}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
