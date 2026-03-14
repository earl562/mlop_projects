"use client";

import { useState, useRef, useCallback, FormEvent } from "react";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import ModeToggle from "@/components/ModeToggle";
import type { AppMode } from "@/components/ModeToggle";
import AnalysisStream from "@/components/AnalysisStream";
import ZoningReport from "@/components/ZoningReport";
import { PipelineStatus, ZoningReportData, streamAnalysis, saveAnalysis } from "@/lib/api";

interface QuickLookupProps {
  onSwitchToChat?: (report: ZoningReportData) => void;
  mode?: AppMode;
  onModeChange?: (mode: AppMode) => void;
}

export default function QuickLookup({ onSwitchToChat, mode = "lookup", onModeChange }: QuickLookupProps) {
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [steps, setSteps] = useState<PipelineStatus[]>([]);
  const [report, setReport] = useState<ZoningReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  const runAnalysis = useCallback(async (address: string) => {
    setIsProcessing(true);
    setSteps([{ step: "connecting", message: "Connecting..." }]);
    setReport(null);
    setError(null);
    setSaveStatus("idle");

    try {
      await streamAnalysis(
        { address },
        (status) => {
          setSteps((prev) => {
            // Mark "connecting" as complete when first real step arrives
            let updated = prev.map((s) =>
              s.step === "connecting" && !s.complete && status.step !== "connecting"
                ? { ...s, complete: true, message: "Connected" }
                : s,
            );
            const existing = updated.findIndex((s) => s.step === status.step);
            if (existing >= 0) {
              updated = [...updated];
              updated[existing] = status;
              return updated;
            }
            return [...updated, status];
          });
        },
        (result) => {
          setReport(result);
          setSteps([]);
        },
        (err) => {
          setError(err);
          setSteps([]);
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
      setSteps([]);
    } finally {
      setIsProcessing(false);
    }
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim()) runAnalysis(input.trim());
  };

  const handleSave = useCallback(async () => {
    if (!report) return;
    setSaveStatus("saving");
    try {
      await saveAnalysis(report);
      setSaveStatus("saved");
    } catch {
      setSaveStatus("error");
    }
  }, [report]);

  const handleReset = useCallback(() => {
    setReport(null);
    setSteps([]);
    setError(null);
    setInput("");
    setSaveStatus("idle");
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8 text-center">
        <h2 className="font-display text-2xl font-bold text-[var(--text-primary)] sm:text-3xl">
          Quick Property Analysis
        </h2>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          Enter an address to get instant zoning analysis, comparable sales, and development potential
        </p>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="mb-8">
        <div
          className="mx-auto flex max-w-xl items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 transition-all focus-within:border-amber-400/60 focus-within:ring-2 focus-within:ring-amber-400/15 sm:px-5 sm:py-3.5"
          style={{ boxShadow: "var(--shadow-elevated)" }}
        >
          <AddressAutocomplete
            inputRef={inputRef}
            value={input}
            onChange={setInput}
            onSelect={(address) => runAnalysis(address)}
            placeholder="Enter a property address..."
            disabled={isProcessing}
          />
          {onModeChange && <ModeToggle mode={mode} onChange={onModeChange} />}
          <button
            type="submit"
            disabled={!input.trim() || isProcessing}
            aria-label="Analyze"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--bg-primary)] transition-all hover:opacity-80 disabled:opacity-20 sm:h-9 sm:w-9"
          >
            {isProcessing ? (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
              </svg>
            )}
          </button>
        </div>
      </form>

      {/* Pipeline progress */}
      {steps.length > 0 && (
        <div className="mx-auto max-w-xl">
          <AnalysisStream steps={steps} error={error} />
        </div>
      )}

      {/* Error */}
      {error && steps.length === 0 && (
        <div className="mx-auto max-w-xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <p className="font-medium">Analysis failed</p>
          <p className="mt-1">{error}</p>
          <button
            onClick={handleReset}
            className="mt-3 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
          >
            Try another address
          </button>
        </div>
      )}

      {/* Results */}
      {report && (
        <div className="space-y-4 animate-fade-up">
          <ZoningReport report={report} />

          {/* Action bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3">
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={saveStatus === "saving" || saveStatus === "saved"}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  saveStatus === "saved"
                    ? "bg-lime-100 text-lime-700"
                    : saveStatus === "error"
                      ? "bg-red-100 text-red-600"
                      : "border border-[var(--border)] bg-white text-[var(--text-secondary)] hover:bg-stone-50"
                }`}
              >
                {saveStatus === "saving"
                  ? "Saving..."
                  : saveStatus === "saved"
                    ? "Saved"
                    : "Save to Portfolio"}
              </button>
              {onSwitchToChat && (
                <button
                  onClick={() => onSwitchToChat(report)}
                  className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100"
                >
                  Chat about this property
                </button>
              )}
            </div>
            <button
              onClick={handleReset}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--text-muted)] transition-colors hover:bg-stone-50 hover:text-[var(--text-secondary)]"
            >
              New analysis
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
