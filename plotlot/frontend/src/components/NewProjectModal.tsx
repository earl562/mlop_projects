"use client";

import { useState, useEffect, useRef } from "react";
import type { ProjectDealType } from "@/lib/workspace";

interface NewProjectModalProps {
  onClose: () => void;
  onCreate: (name: string, dealType: ProjectDealType, description: string) => void;
}

const DEAL_TYPE_OPTIONS: { value: ProjectDealType; label: string }[] = [
  { value: "land_deal", label: "Land Deal" },
  { value: "wholesale", label: "Wholesale" },
  { value: "creative_finance", label: "Creative Finance" },
  { value: "hybrid", label: "Hybrid" },
];

export default function NewProjectModal({ onClose, onCreate }: NewProjectModalProps) {
  const [name, setName] = useState("");
  const [dealType, setDealType] = useState<ProjectDealType>(null);
  const [description, setDescription] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  // Focus name input on open
  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onCreate(trimmed, dealType, description.trim());
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className="fixed left-1/2 top-1/2 z-[70] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border shadow-[var(--shadow-elevated)]"
        style={{
          background: "var(--bg-surface)",
          borderColor: "var(--border-soft)",
        }}
        role="dialog"
        aria-modal="true"
        aria-label="Create new project"
      >
        {/* Header */}
        <div
          className="flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--border-soft)" }}
        >
          <h2
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            New Project
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-[var(--bg-inset)]"
            aria-label="Close"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ color: "var(--text-muted)" }}
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-5 py-5">
          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="project-name"
              className="text-xs font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Name <span style={{ color: "var(--danger)" }}>*</span>
            </label>
            <input
              id="project-name"
              ref={nameRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Hollywood Multifamily Infill"
              maxLength={80}
              className="w-full rounded-xl border bg-transparent px-3 py-2.5 text-sm outline-none transition-all focus:border-[var(--brand-soft-border)] focus:shadow-[var(--shadow-card)]"
              style={{
                borderColor: "var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          {/* Deal type */}
          <div className="flex flex-col gap-1.5">
            <span
              className="text-xs font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Deal Type <span style={{ color: "var(--text-muted)" }}>(optional)</span>
            </span>
            <div className="grid grid-cols-2 gap-2">
              {DEAL_TYPE_OPTIONS.map((opt) => {
                const isSelected = dealType === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDealType(isSelected ? null : opt.value)}
                    className="rounded-xl border px-3 py-2 text-left text-xs font-medium transition-all"
                    style={{
                      borderColor: isSelected
                        ? "var(--brand-soft-border)"
                        : "var(--border-soft)",
                      background: isSelected ? "var(--brand-subtle)" : "transparent",
                      color: isSelected ? "var(--brand-strong)" : "var(--text-secondary)",
                    }}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Description */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="project-description"
              className="text-xs font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Description <span style={{ color: "var(--text-muted)" }}>(optional)</span>
            </label>
            <textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Infill opportunities in Broward County under $500K"
              rows={2}
              maxLength={200}
              className="w-full resize-none rounded-xl border bg-transparent px-3 py-2.5 text-sm outline-none transition-all focus:border-[var(--brand-soft-border)] focus:shadow-[var(--shadow-card)]"
              style={{
                borderColor: "var(--border)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border py-2.5 text-sm font-medium transition-colors hover:bg-[var(--bg-inset)]"
              style={{
                borderColor: "var(--border-soft)",
                color: "var(--text-secondary)",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim()}
              className="flex-1 rounded-xl py-2.5 text-sm font-medium text-white transition-opacity disabled:opacity-40"
              style={{ background: "var(--brand-strong)" }}
            >
              Create Project
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
