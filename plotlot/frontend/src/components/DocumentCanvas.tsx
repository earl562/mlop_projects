"use client";

import { useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import DocumentGenerator from "@/components/DocumentGenerator";
import type { ZoningReportData } from "@/lib/api";

interface DocumentCanvasProps {
  report: ZoningReportData;
  isOpen: boolean;
  onClose: () => void;
}

export default function DocumentCanvas({ report, isOpen, onClose }: DocumentCanvasProps) {
  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleEscape]);

  if (!isOpen) return null;

  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Document Generator"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative z-10 flex h-[calc(100dvh-2rem)] w-[90vw] max-w-4xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl sm:h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Document Generator
            </h2>
            <p className="text-xs text-[var(--text-muted)]">
              {report.formatted_address || report.address}
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface-raised)] hover:text-[var(--text-secondary)]"
            aria-label="Close document generator"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          <DocumentGenerator report={report} />
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(modal, document.body);
}
