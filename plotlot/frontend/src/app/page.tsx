"use client";

import { useState, useRef, useEffect, useCallback, FormEvent } from "react";
import ZoningReport from "@/components/ZoningReport";
import AnalysisStream from "@/components/AnalysisStream";
import {
  PipelineStatus,
  ZoningReportData,
  ChatMessageData,
  ToolUseEvent,
  streamAnalysis,
  streamChat,
  saveAnalysis,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ToolActivity {
  tool: string;
  message: string;
  status: "running" | "complete";
}

interface DisplayMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  isStreaming?: boolean;
  // Embedded rich content
  pipelineSteps?: PipelineStatus[];
  report?: ZoningReportData;
  saveStatus?: "idle" | "saving" | "saved" | "error";
  toolActivity?: ToolActivity[];
}

// ---------------------------------------------------------------------------
// Address detection heuristic
// ---------------------------------------------------------------------------

const FL_PATTERNS = /\b(miami|fort lauderdale|hollywood|hialeah|pembroke|miramar|coral|doral|homestead|aventura|boca|delray|boynton|west palm|palm beach|broward|dade|FL|florida)\b/i;
const ADDRESS_PATTERN = /\d+\s+\w+\s+(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ter|terrace|ct|court|ln|lane|way|pl|place|cir|circle)\b/i;

function extractAddress(text: string): string | null {
  // Must look like it has a street address AND a Florida reference
  if (ADDRESS_PATTERN.test(text) && FL_PATTERNS.test(text)) {
    return text.trim();
  }
  // Or user explicitly asks to "analyze" or "look up" something with FL references
  if (/\b(analyze|look up|lookup|check|search|zoning for|what can .* build)\b/i.test(text) && FL_PATTERNS.test(text)) {
    // Try to extract just the address part
    const match = text.match(/\d+\s+[\w\s]+(?:,\s*[\w\s]+){0,3}/);
    if (match) return match[0].trim();
    return text.replace(/^.*?(analyze|look up|lookup|check|search|zoning for)\s*/i, "").trim();
  }
  return null;
}

// ---------------------------------------------------------------------------
// Suggestions for fresh conversation
// ---------------------------------------------------------------------------

const WELCOME_SUGGESTIONS = [
  { label: "171 NE 209th Ter, Miami, FL 33179", desc: "Miami Gardens" },
  { label: "2600 SW 3rd Ave, Miami, FL 33129", desc: "Miami" },
  { label: "1600 S Andrews Ave, Fort Lauderdale, FL 33316", desc: "Fort Lauderdale" },
];

const FOLLOWUP_SUGGESTIONS = [
  "What can I build on this lot?",
  "Explain the density calculation",
  "What setback variances could I request?",
  "Is this suitable for multifamily?",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

let msgCounter = 0;

export default function Home() {
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      id: msgCounter++,
      role: "assistant",
      content:
        "Hey! I'm PlotLot, your South Florida zoning analyst. Give me any address in Miami-Dade, Broward, or Palm Beach County and I'll analyze what you can build there. Or just ask me a zoning question.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentReport, setCurrentReport] = useState<ZoningReportData | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on load
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const addMessage = useCallback((msg: Omit<DisplayMessage, "id">) => {
    const newMsg = { ...msg, id: msgCounter++ };
    setMessages((prev) => [...prev, newMsg]);
    return newMsg.id;
  }, []);

  const updateMessage = useCallback((id: number, updates: Partial<DisplayMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    );
  }, []);

  // Run the full analysis pipeline, showing progress in chat
  const runAnalysis = useCallback(
    async (address: string) => {
      // Add a system message for pipeline progress
      const progressId = addMessage({
        role: "system",
        content: "",
        pipelineSteps: [],
      });

      try {
        let finalReport: ZoningReportData | null = null;

        await streamAnalysis(
          address,
          (status) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== progressId) return m;
                const steps = m.pipelineSteps || [];
                const existing = steps.findIndex((s) => s.step === status.step);
                if (existing >= 0) {
                  const updated = [...steps];
                  updated[existing] = status;
                  return { ...m, pipelineSteps: updated };
                }
                return { ...m, pipelineSteps: [...steps, status] };
              }),
            );
          },
          (report) => {
            finalReport = report;
            setCurrentReport(report);
            // Update the progress message to include the report
            updateMessage(progressId, { report, pipelineSteps: undefined });
          },
          (error) => {
            updateMessage(progressId, {
              role: "assistant",
              content: `I couldn't analyze that address: ${error}`,
              pipelineSteps: undefined,
            });
          },
        );

        if (finalReport) {
          const r = finalReport as ZoningReportData;
          // Add a summary chat message after the report
          const summary = [];
          summary.push(`**${r.zoning_district}** — ${r.zoning_description} in ${r.municipality}, ${r.county} County.`);
          if (r.density_analysis) {
            summary.push(`Max **${r.density_analysis.max_units} unit(s)** (governed by ${r.density_analysis.governing_constraint}).`);
          }
          if (r.summary) summary.push(r.summary);
          summary.push("\nAsk me anything about this property's zoning.");

          addMessage({
            role: "assistant",
            content: summary.join(" "),
          });
        }
      } catch (err) {
        updateMessage(progressId, {
          role: "assistant",
          content: `Connection error: ${err instanceof Error ? err.message : "Failed to reach backend"}`,
          pipelineSteps: undefined,
        });
      }
    },
    [addMessage, updateMessage],
  );

  // Send a chat message (with or without analysis)
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isProcessing) return;
      setIsProcessing(true);
      setInput("");

      // Add user message
      addMessage({ role: "user", content: text.trim() });

      // Check if this looks like an address to analyze
      const address = extractAddress(text);
      if (address && !currentReport) {
        // First analysis — run full pipeline
        await runAnalysis(address);
        setIsProcessing(false);
        return;
      }

      if (address && currentReport) {
        // User wants to analyze a NEW address
        setCurrentReport(null);
        await runAnalysis(address);
        setIsProcessing(false);
        return;
      }

      // Regular chat — stream response with report context
      const assistantId = addMessage({
        role: "assistant",
        content: "",
        isStreaming: true,
        toolActivity: [],
      });

      // Build history from previous messages (skip system/report messages)
      const history: ChatMessageData[] = messages
        .filter((m) => m.role === "user" || (m.role === "assistant" && m.content))
        .slice(-10) // last 10 messages for context window
        .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));

      try {
        await streamChat(
          text.trim(),
          history,
          currentReport,
          (token) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId && m.isStreaming
                  ? { ...m, content: m.content + token }
                  : m,
              ),
            );
          },
          () => {
            updateMessage(assistantId, { isStreaming: false });
          },
          (error) => {
            updateMessage(assistantId, {
              content: `Error: ${error}`,
              isStreaming: false,
            });
          },
          sessionId,
          (newSessionId) => {
            setSessionId(newSessionId);
          },
          (toolEvent: ToolUseEvent) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const tools = m.toolActivity || [];
                return {
                  ...m,
                  toolActivity: [...tools, { tool: toolEvent.tool, message: toolEvent.message, status: "running" as const }],
                };
              }),
            );
          },
          (toolName: string) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const tools = (m.toolActivity || []).map((t) =>
                  t.tool === toolName ? { ...t, status: "complete" as const } : t,
                );
                return { ...m, toolActivity: tools };
              }),
            );
          },
        );
      } catch {
        updateMessage(assistantId, {
          content: "Connection failed. Is the backend running?",
          isStreaming: false,
        });
      }

      setIsProcessing(false);
    },
    [messages, isProcessing, currentReport, sessionId, addMessage, updateMessage, runAnalysis],
  );

  const handleSave = useCallback(
    async (msgId: number, report: ZoningReportData) => {
      updateMessage(msgId, { saveStatus: "saving" });
      try {
        await saveAnalysis(report);
        updateMessage(msgId, { saveStatus: "saved" });
      } catch {
        updateMessage(msgId, { saveStatus: "error" });
      }
    },
    [updateMessage],
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const hasReport = messages.some((m) => m.report);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg) => (
            <div key={msg.id}>
              {/* Pipeline progress */}
              {msg.pipelineSteps && msg.pipelineSteps.length > 0 && !msg.report && (
                <div className="mx-auto max-w-lg">
                  <AnalysisStream steps={msg.pipelineSteps} error={null} />
                </div>
              )}

              {/* Embedded report */}
              {msg.report && (
                <div className="space-y-3">
                  <ZoningReport report={msg.report} />
                  <div className="flex justify-end">
                    <button
                      onClick={() => handleSave(msg.id, msg.report!)}
                      disabled={msg.saveStatus === "saving" || msg.saveStatus === "saved"}
                      className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors ${
                        msg.saveStatus === "saved"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : msg.saveStatus === "error"
                            ? "bg-red-500/20 text-red-400"
                            : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                      }`}
                    >
                      {msg.saveStatus === "saving"
                        ? "Saving..."
                        : msg.saveStatus === "saved"
                          ? "Saved to Portfolio"
                          : "Save to Portfolio"}
                    </button>
                  </div>
                </div>
              )}

              {/* Tool activity indicators */}
              {msg.toolActivity && msg.toolActivity.length > 0 && (
                <div className="flex justify-start mb-2">
                  <div className="flex items-start gap-3 max-w-[85%]">
                    <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-xs font-black text-white">
                      P
                    </div>
                    <div className="space-y-1">
                      {msg.toolActivity.map((t, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-zinc-400">
                          {t.status === "running" ? (
                            <svg className="h-3.5 w-3.5 animate-spin text-amber-400" viewBox="0 0 24 24" fill="none">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <svg className="h-3.5 w-3.5 text-emerald-400" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          )}
                          <span className={t.status === "complete" ? "text-zinc-500" : "text-zinc-300"}>{t.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Regular message bubble */}
              {msg.content && msg.role !== "system" && (
                <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className="flex items-start gap-3 max-w-[85%]">
                    {msg.role === "assistant" && (
                      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-xs font-black text-white">
                        P
                      </div>
                    )}
                    <div
                      className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "bg-emerald-600 text-white"
                          : "bg-zinc-800/80 text-zinc-200"
                      }`}
                    >
                      {msg.content}
                      {msg.isStreaming && msg.content && (
                        <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-emerald-400" />
                      )}
                      {msg.isStreaming && !msg.content && (
                        <span className="inline-flex items-center gap-1 text-zinc-500">
                          <span className="animate-pulse">Thinking</span>
                          <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                          <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
                          <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Suggestions */}
      <div className="mx-auto w-full max-w-3xl px-4">
        {!hasReport && messages.length <= 1 && (
          <div className="mb-3 flex flex-wrap gap-2">
            <span className="text-xs text-zinc-500">Try an address:</span>
            {WELCOME_SUGGESTIONS.map((s) => (
              <button
                key={s.label}
                onClick={() => sendMessage(s.label)}
                disabled={isProcessing}
                className="rounded-lg bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-40"
              >
                <span className="font-medium text-zinc-300">{s.desc}:</span> {s.label}
              </button>
            ))}
          </div>
        )}
        {hasReport && !isProcessing && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.isStreaming && (
          <div className="mb-3 flex flex-wrap gap-2">
            {FOLLOWUP_SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                disabled={isProcessing}
                className="rounded-lg bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="border-t border-zinc-800/50 bg-zinc-950 px-4 py-4">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex gap-3">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={hasReport ? "Ask about this property's zoning..." : "Enter a South Florida address or ask a zoning question..."}
              disabled={isProcessing}
              className="flex-1 rounded-xl border border-zinc-700 bg-zinc-800/50 px-4 py-3 text-sm text-white placeholder-zinc-500 outline-none ring-emerald-500/40 transition-all focus:border-emerald-500 focus:ring-2"
            />
            <button
              type="submit"
              disabled={!input.trim() || isProcessing}
              className="rounded-xl bg-emerald-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isProcessing ? (
                <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              )}
            </button>
          </div>
          <p className="mt-2 text-center text-xs text-zinc-600">
            PlotLot covers 104 municipalities across Miami-Dade, Broward &amp; Palm Beach counties
          </p>
        </form>
      </div>
    </div>
  );
}
