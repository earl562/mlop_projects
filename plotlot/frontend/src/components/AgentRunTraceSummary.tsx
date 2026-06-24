"use client";

import { AlertTriangle, CheckCircle2, Database, ExternalLink, FileText, GitBranch } from "lucide-react";

import type { AgentRunTraceData, AgentRunTraceEvidencePacket } from "@/lib/agentRunTrace";
import AgentRunTraceReportSections from "./AgentRunTraceReportSections";
import AgentRunSourceRetrievals from "./AgentRunSourceRetrievals";
import AgentRunTraceAssumptions from "./AgentRunTraceAssumptions";
import AgentRunTraceOpportunities from "./AgentRunTraceOpportunities";
import SafeExternalLink from "./SafeExternalLink";

export default function AgentRunTraceSummary({
  trace,
}: {
  readonly trace: AgentRunTraceData | null;
}) {
  if (trace === null) return null;

  const statusLabel = trace.replay_ready ? "Replay ready" : "Replay needs review";
  const latestEvalStatus = trace.latest_eval?.status ?? "not scored";
  const trend = trace.improvement?.improvement_status ?? "not available";

  return (
    <div className="mt-4 border-t border-[var(--border-soft)] pt-3" data-testid="agent-run-trace">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-[var(--brand)]" aria-hidden="true" />
          <h4 className="text-xs font-semibold text-[var(--text-primary)]">Replay trace</h4>
        </div>
        <span className={traceStatusClass(trace.replay_ready)}>
          {trace.replay_ready ? (
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          )}
          {statusLabel}
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <TraceMetric label="Trace steps" value={trace.trace_steps.length.toString()} />
        <TraceMetric label="Lanes" value={trace.assignments.length.toString()} />
        <TraceMetric label="Evidence IDs" value={trace.evidence_ids.length.toString()} />
        <TraceMetric label="Latest eval" value={latestEvalStatus} />
      </div>

      <div className="mt-3 grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-2">
        <TraceArtifact label="Report" value={trace.artifact.report_id} />
        <TraceArtifact label="Document" value={trace.artifact.document_id} />
      </div>

      <AgentRunTraceReportSections sections={trace.artifact.sections} />
      <AgentRunTraceOpportunities opportunities={trace.artifact.opportunities} />
      <AgentRunTraceAssumptions assumptions={trace.artifact.assumptions} />

      <div className="mt-3 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">Improvement trend</span>
        <span className="mx-2 text-[var(--text-muted)]">/</span>
        <span>{trend}</span>
      </div>

      {trace.evidence_packets.length > 0 && <EvidencePacketSummary packets={trace.evidence_packets} />}
      <AgentRunSourceRetrievals retrievals={trace.source_retrievals} />

      {trace.missing_replay_requirements.length > 0 && (
        <div className="mt-2 rounded-lg border border-[var(--warning)] bg-[var(--brand-subtle)] px-3 py-2 text-xs text-[var(--warning)]">
          Missing {trace.missing_replay_requirements.join(", ")}
        </div>
      )}
    </div>
  );
}

function EvidencePacketSummary({
  packets,
}: {
  readonly packets: readonly AgentRunTraceEvidencePacket[];
}) {
  return (
    <div className="mt-3" data-testid="agent-run-evidence-packets">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-[var(--brand)]" aria-hidden="true" />
          <h5 className="text-xs font-semibold text-[var(--text-primary)]">Evidence packets</h5>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {packetCountLabel(packets.length)}
        </span>
      </div>

      <div className="space-y-2">
        {packets.map((packet) => (
          <EvidencePacketRow key={packet.evidence_id} packet={packet} />
        ))}
      </div>
    </div>
  );
}

function EvidencePacketRow({ packet }: { readonly packet: AgentRunTraceEvidencePacket }) {
  const flags = [...packet.quality_flags, ...packet.warnings];
  return (
    <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <SafeExternalLink
            href={packet.source_url}
            className="inline-flex max-w-full items-center gap-1 text-xs font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
          >
            <span className="truncate">{packet.source_title}</span>
            <ExternalLink className="h-3 w-3 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
          </SafeExternalLink>
          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-secondary)]">
            <span className="font-mono">{packet.evidence_id}</span>
            <span>{packet.source_authority}</span>
            <span>{packet.source_type}</span>
          </div>
        </div>
        <span className={packetQualityClass(packet)}>
          {formatScore(packet.quality_score)} quality
        </span>
      </div>

      <div className="mt-2 grid gap-2 text-[10px] text-[var(--text-secondary)] sm:grid-cols-2">
        <PacketFact label="Schema" value={packet.schema_version} />
        <PacketFact label="Parser" value={packet.parser_version} />
        <PacketFact label="Fields" value={packet.referenced_field_keys.join(", ") || "None"} />
        <PacketFact label="Outputs" value={packet.calculation_outputs.join(", ") || "None"} />
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {packet.lineage.map((item) => (
          <TraceChip key={`${packet.evidence_id}-lineage-${item}`} value={item} tone="neutral" />
        ))}
        {flags.length === 0 ? (
          <TraceChip value="No packet warnings" tone="success" />
        ) : (
          flags.map((item) => (
            <TraceChip key={`${packet.evidence_id}-flag-${item}`} value={item} tone="warning" />
          ))
        )}
      </div>
    </div>
  );
}

function PacketFact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-w-0">
      <span className="font-semibold text-[var(--text-primary)]">{label}</span>
      <span className="mx-1 text-[var(--text-muted)]">/</span>
      <span className="break-words font-mono">{value}</span>
    </div>
  );
}

function TraceChip({
  value,
  tone,
}: {
  readonly value: string;
  readonly tone: "neutral" | "success" | "warning";
}) {
  return <span className={traceChipClass(tone)}>{value}</span>;
}

function TraceMetric({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-h-[58px] rounded-lg bg-[var(--bg-surface)] px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function TraceArtifact({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string | null;
}) {
  return (
    <div className="flex min-h-[40px] items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2">
      <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          {label}
        </div>
        <div className="truncate font-mono text-xs font-semibold text-[var(--text-primary)]">
          {value ?? "Not recorded"}
        </div>
      </div>
    </div>
  );
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function packetCountLabel(count: number): string {
  return count === 1 ? "1 packet" : `${count} packets`;
}

function traceStatusClass(ready: boolean): string {
  const base = "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold";
  if (ready) {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
}

function packetQualityClass(packet: AgentRunTraceEvidencePacket): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-semibold";
  if (packet.quality_score >= 0.9 && packet.warnings.length === 0) {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  if (packet.quality_score >= 0.75) {
    return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
  }
  return `${base} border-[var(--danger)] bg-[var(--danger-subtle)] text-[var(--danger)]`;
}

function traceChipClass(tone: "neutral" | "success" | "warning"): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-medium";
  if (tone === "success") {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  if (tone === "warning") {
    return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
  }
  return `${base} border-[var(--border-soft)] text-[var(--text-secondary)]`;
}
