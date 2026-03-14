"use client";

import { useState, useCallback } from "react";

interface PipelineStep {
  key: string;
  label: string;
  description: string;
  required: boolean;
}

const PIPELINE_STEPS: PipelineStep[] = [
  {
    key: "search",
    label: "Zoning Search",
    description: "Search ordinance database for zoning rules",
    required: true,
  },
  {
    key: "analysis",
    label: "AI Analysis",
    description: "Extract dimensional standards from zoning code",
    required: true,
  },
  {
    key: "calculation",
    label: "Density Calculation",
    description: "Compute max allowable units (4-constraint model)",
    required: false,
  },
  {
    key: "comps",
    label: "Comparable Sales",
    description: "Find recent land sales within 3-mile radius",
    required: false,
  },
  {
    key: "proforma",
    label: "Pro Forma",
    description: "Residual land valuation (GDV - costs - margin)",
    required: false,
  },
];

interface PipelineApprovalProps {
  address: string;
  dealType: string;
  onApprove: (skipSteps: string[]) => void;
  onCancel: () => void;
  disabled?: boolean;
}

export default function PipelineApproval({
  address,
  dealType,
  onApprove,
  onCancel,
  disabled = false,
}: PipelineApprovalProps) {
  const [enabledSteps, setEnabledSteps] = useState<Record<string, boolean>>(
    () => Object.fromEntries(PIPELINE_STEPS.map((s) => [s.key, true])),
  );

  const toggleStep = useCallback((key: string) => {
    setEnabledSteps((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const handleApprove = useCallback(() => {
    const skipSteps = PIPELINE_STEPS
      .filter((s) => !s.required && !enabledSteps[s.key])
      .map((s) => s.key);
    onApprove(skipSteps);
  }, [enabledSteps, onApprove]);

  const dealLabel = dealType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 sm:p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Pipeline Plan
        </h3>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          I&apos;ll analyze <span className="font-medium text-[var(--text-secondary)]">{address}</span> as a{" "}
          <span className="font-medium text-amber-600">{dealLabel}</span>.
          Uncheck any steps you want to skip.
        </p>
      </div>

      <div className="space-y-2">
        {PIPELINE_STEPS.map((step) => {
          const isEnabled = enabledSteps[step.key];
          return (
            <label
              key={step.key}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors cursor-pointer ${
                step.required
                  ? "border-transparent bg-transparent cursor-default"
                  : isEnabled
                    ? "border-amber-200 bg-amber-50/50 dark:border-amber-800/50 dark:bg-amber-950/20"
                    : "border-[var(--border)] bg-[var(--bg-surface-raised)] opacity-60"
              }`}
            >
              <input
                type="checkbox"
                checked={isEnabled}
                onChange={() => !step.required && toggleStep(step.key)}
                disabled={step.required || disabled}
                className="h-4 w-4 rounded border-[var(--border)] text-amber-600 accent-amber-600 disabled:opacity-50"
              />
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium text-[var(--text-secondary)]">
                  {step.label}
                  {step.required && (
                    <span className="ml-1.5 text-[10px] font-normal text-[var(--text-muted)]">
                      required
                    </span>
                  )}
                </span>
                <p className="text-xs text-[var(--text-muted)]">{step.description}</p>
              </div>
            </label>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          onClick={onCancel}
          disabled={disabled}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] disabled:opacity-40"
        >
          Cancel
        </button>
        <button
          onClick={handleApprove}
          disabled={disabled}
          className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-700 disabled:opacity-40"
        >
          Run Analysis
        </button>
      </div>
    </div>
  );
}
