"use client";

import { motion } from "framer-motion";
import type { ZoningReportData } from "@/lib/api";
import { springGentle } from "@/lib/motion";
import { CitationBadge } from "./ReportShared";

interface EvidencePanelProps {
  report: ZoningReportData;
}

export default function EvidencePanel({ report }: EvidencePanelProps) {
  const { source_refs, confidence_warning, suggested_next_steps, density_analysis } = report;
  const notes = density_analysis?.notes ?? [];
  const hasAnything = (source_refs && source_refs.length > 0) || notes.length > 0 || confidence_warning || (suggested_next_steps && suggested_next_steps.length > 0);

  if (!hasAnything) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={springGentle}
        className="flex flex-col items-center justify-center py-12 text-center"
      >
        <svg className="mb-3 h-8 w-8 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        <p className="text-sm text-[var(--text-muted)]">No evidence data available for this analysis.</p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={springGentle}
      className="space-y-6"
      data-testid="report-section-evidence"
    >
      {/* Source Citations */}
      {source_refs && source_refs.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">
            Source Citations
            <span className="ml-2 font-normal normal-case text-blue-500">{source_refs.length} chunk{source_refs.length !== 1 ? "s" : ""} retrieved</span>
          </h3>
          <div className="space-y-2">
            {source_refs.map((ref, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] p-3"
              >
                <CitationBadge sourceRef={ref} index={i} />
                <div className="min-w-0 flex-1">
                  {ref.section_title && (
                    <p className="text-xs font-medium text-[var(--text-primary)]">{ref.section_title}</p>
                  )}
                  {ref.section && (
                    <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">{ref.section}</p>
                  )}
                  {ref.chunk_text_preview && (
                    <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-[var(--text-secondary)]">
                      &ldquo;{ref.chunk_text_preview}&rdquo;
                    </p>
                  )}
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                    Relevance score: {(ref.score * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Calculator Notes */}
      {notes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Calculator Notes</h3>
          <div className="space-y-1.5">
            {notes.map((note, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                <span className="mt-0.5 shrink-0 text-[var(--text-muted)]">·</span>
                <span>{note}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open Questions */}
      {(confidence_warning || (suggested_next_steps && suggested_next_steps.length > 0)) && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/20">
          <h3 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-400">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            Open Questions
          </h3>
          {confidence_warning && (
            <p className="text-xs text-amber-800 dark:text-amber-300">{confidence_warning}</p>
          )}
          {suggested_next_steps && suggested_next_steps.length > 0 && (
            <ul className="space-y-1">
              {suggested_next_steps.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300">
                  <span className="mt-0.5 shrink-0 font-bold">{i + 1}.</span>
                  <span>{step}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </motion.div>
  );
}
