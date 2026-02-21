"use client";

import { useState, useRef, useEffect, useCallback, FormEvent, useId } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  isStreaming?: boolean;
  pipelineSteps?: PipelineStatus[];
  report?: ZoningReportData;
  saveStatus?: "idle" | "saving" | "saved" | "error";
  toolActivity?: ToolActivity[];
}

// ---------------------------------------------------------------------------
// Address detection heuristic
// ---------------------------------------------------------------------------

const FL_PATTERNS = /\b(miami|fort lauderdale|hollywood|hialeah|pembroke|miramar|coral|doral|homestead|aventura|boca|delray|boynton|west palm|palm beach|broward|dade|FL|florida)\b/i;
const ADDRESS_PATTERN = /\d+\s+(?:\w+\s+)+(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ter|terrace|ct|court|ln|lane|way|pl|place|cir|circle|pkwy|parkway|hwy|highway|trl|trail|real|path)\b/i;
// Broader fallback: "123 Something, City, FL 33xxx" pattern (number + comma + FL indicator + zip)
const ADDRESS_WITH_ZIP = /\d+\s+[\w\s]+,\s*[\w\s]+,\s*FL\s+\d{5}/i;

function extractAddress(text: string): string | null {
  if (ADDRESS_PATTERN.test(text) && FL_PATTERNS.test(text)) {
    return text.trim();
  }
  if (ADDRESS_WITH_ZIP.test(text)) {
    return text.trim();
  }
  if (/\b(analyze|look up|lookup|check|search|zoning (?:for|rules|regulations|code)|what can .* build)\b/i.test(text) && FL_PATTERNS.test(text)) {
    const match = text.match(/\d+\s+[\w\s]+(?:,\s*[\w\s]+){0,3}/);
    if (match) return match[0].trim();
    return text.replace(/^.*?(analyze|look up|lookup|check|search|zoning (?:for|rules|regulations|code))\s*/i, "").trim();
  }
  return null;
}

// ---------------------------------------------------------------------------
// Suggestions
// ---------------------------------------------------------------------------

const WELCOME_SUGGESTIONS = [
  { label: "Analyze a property in Miami Gardens", icon: "\u{1F3E0}" },
  { label: "Find vacant lots in Miami-Dade", icon: "\u{1F4CA}" },
  { label: "Zoning rules in Miramar", icon: "\u{1F4CB}" },
  { label: "What can I build on my lot?", icon: "\u{1F3D7}\uFE0F" },
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

export default function Home() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentReport, setCurrentReport] = useState<ZoningReportData | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const idPrefix = useId();
  const msgCounterRef = useRef(0);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Re-focus input on mount and when switching from welcome to conversation
  const isWelcome = messages.length === 0;
  useEffect(() => {
    inputRef.current?.focus();
  }, [isWelcome]);

  const addMessage = useCallback((msg: Omit<DisplayMessage, "id">) => {
    const newMsg = { ...msg, id: `${idPrefix}-${msgCounterRef.current++}` };
    setMessages((prev) => [...prev, newMsg]);
    return newMsg.id;
  }, [idPrefix]);

  const updateMessage = useCallback((id: string, updates: Partial<DisplayMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    );
  }, []);

  // Run the full analysis pipeline
  const runAnalysis = useCallback(
    async (address: string) => {
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

  // Send a chat message
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isProcessing) return;
      setIsProcessing(true);
      setInput("");

      addMessage({ role: "user", content: text.trim() });

      const address = extractAddress(text);
      if (address && !currentReport) {
        await runAnalysis(address);
        setIsProcessing(false);
        return;
      }

      if (address && currentReport) {
        setCurrentReport(null);
        await runAnalysis(address);
        setIsProcessing(false);
        return;
      }

      // Regular chat
      const assistantId = addMessage({
        role: "assistant",
        content: "",
        isStreaming: true,
        toolActivity: [],
      });

      const history: ChatMessageData[] = [
        ...messages
          .filter((m) => m.role === "user" || (m.role === "assistant" && m.content))
          .slice(-9)
          .map((m) => ({ role: m.role as "user" | "assistant", content: m.content })),
        { role: "user" as const, content: text.trim() },
      ];

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
          (fullContent: string) => {
            updateMessage(assistantId, { content: fullContent, isStreaming: false });
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
    async (msgId: string, report: ZoningReportData) => {
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

  // ─── Welcome State ────────────────────────────────────────────────────
  if (isWelcome) {
    return (
      <div className="flex h-[calc(100vh-3rem)] flex-col items-center justify-center px-4">
        {/* Greeting */}
        <div className="mb-8 text-center animate-fade-up">
          <div className="mb-3 flex items-center justify-center gap-2 animate-fade-up delay-1">
            <svg className="h-5 w-5 text-amber-600" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 2L12.5 7.5L18 10L12.5 12.5L10 18L7.5 12.5L2 10L7.5 7.5L10 2Z" clipRule="evenodd" />
            </svg>
            <span className="text-lg font-medium text-stone-500">Hi there</span>
          </div>
          <h1 className="text-4xl font-semibold tracking-tight text-stone-800 animate-fade-up delay-2">
            Analyze any property in South Florida
          </h1>
          <p className="mt-2 text-sm text-stone-400 animate-fade-up delay-3">
            Zoning codes, density limits, and development potential — in seconds
          </p>
        </div>

        {/* Input bar */}
        <form onSubmit={handleSubmit} className="mb-6 w-full max-w-2xl animate-fade-up delay-3">
          <div className="flex items-center gap-2 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-lg transition-all focus-within:border-amber-400 focus-within:ring-2 focus-within:ring-amber-400/20">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Enter a South Florida address or ask a question..."
              disabled={isProcessing}
              className="flex-1 bg-transparent text-sm text-stone-800 placeholder-stone-400 outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || isProcessing}
              aria-label="Send message"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-700 text-white transition-colors hover:bg-amber-600 disabled:opacity-30"
            >
              {isProcessing ? (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              )}
            </button>
          </div>
        </form>

        {/* Suggestion chips */}
        <div className="flex flex-wrap justify-center gap-2.5 animate-fade-up delay-4">
          {WELCOME_SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              onClick={() => sendMessage(s.label)}
              disabled={isProcessing}
              className="rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-600 shadow-sm transition-all hover:border-amber-300 hover:bg-amber-50/50 hover:shadow-md hover:-translate-y-0.5 disabled:opacity-40"
            >
              <span className="mr-1.5">{s.icon}</span>
              {s.label}
            </button>
          ))}
        </div>

        {/* Footer */}
        <p className="mt-10 text-center text-xs text-stone-400 animate-fade-in delay-4">
          PlotLot covers 104 municipalities across Miami-Dade, Broward &amp; Palm Beach counties
        </p>
      </div>
    );
  }

  // ─── Conversation State ───────────────────────────────────────────────
  return (
    <div className="relative flex h-[calc(100vh-3rem)] flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto pb-52">
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-6">
          {messages.map((msg) => (
            <div key={msg.id} className="animate-fade-up">
              {/* Pipeline progress — inline stepper */}
              {msg.pipelineSteps && msg.pipelineSteps.length > 0 && !msg.report && (
                <div className="flex items-start gap-3">
                  <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-[10px] font-black text-white">
                    P
                  </div>
                  <AnalysisStream steps={msg.pipelineSteps} error={null} />
                </div>
              )}

              {/* Embedded report */}
              {msg.report && (
                <div className="space-y-3">
                  <ZoningReport report={msg.report} />
                  {msg.report.confidence_warning && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                      <div className="flex items-start gap-2.5">
                        <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                        </svg>
                        <div>
                          <p className="text-sm font-medium text-amber-800">{msg.report.confidence_warning}</p>
                          {msg.report.suggested_next_steps && msg.report.suggested_next_steps.length > 0 && (
                            <ul className="mt-1.5 space-y-0.5">
                              {msg.report.suggested_next_steps.map((step, i) => (
                                <li key={i} className="text-xs text-amber-700">&#8226; {step}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="flex justify-end">
                    <button
                      onClick={() => handleSave(msg.id, msg.report!)}
                      disabled={msg.saveStatus === "saving" || msg.saveStatus === "saved"}
                      className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors ${
                        msg.saveStatus === "saved"
                          ? "bg-lime-100 text-lime-700"
                          : msg.saveStatus === "error"
                            ? "bg-red-100 text-red-600"
                            : "border border-stone-200 bg-white text-stone-600 hover:bg-stone-50"
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
                <div className="mb-2 flex justify-start">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-[10px] font-black text-white">
                      P
                    </div>
                    <div className="space-y-1">
                      {msg.toolActivity.map((t, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-stone-500">
                          {t.status === "running" ? (
                            <div className="h-2 w-2 rounded-full bg-amber-500 animate-pulse-dot" />
                          ) : (
                            <svg className="h-3.5 w-3.5 text-stone-400" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          )}
                          <span className={t.status === "complete" ? "text-stone-400" : "text-stone-600"}>{t.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Regular message */}
              {msg.content && msg.role !== "system" && (
                <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "user" ? (
                    /* User message — right-aligned plain text, no bubble */
                    <div className="max-w-[75%] text-sm leading-relaxed text-stone-600">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant message — left-aligned with avatar */
                    <div className="flex items-start gap-3 max-w-[85%]">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-[10px] font-black text-white">
                        P
                      </div>
                      <div className="text-sm leading-relaxed text-stone-700 min-w-0">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            strong: ({ children }) => <strong className="font-semibold text-stone-800">{children}</strong>,
                            ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
                            li: ({ children }) => <li>{children}</li>,
                            h1: ({ children }) => <h1 className="mb-2 text-lg font-bold text-stone-800">{children}</h1>,
                            h2: ({ children }) => <h2 className="mb-2 text-base font-bold text-stone-800">{children}</h2>,
                            h3: ({ children }) => <h3 className="mb-1 text-sm font-bold text-stone-800">{children}</h3>,
                            a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-amber-700 underline hover:text-amber-600">{children}</a>,
                            code: ({ children }) => <code className="rounded bg-stone-100 px-1.5 py-0.5 text-xs font-mono text-stone-700">{children}</code>,
                            pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded-lg bg-stone-100 p-3 text-xs">{children}</pre>,
                            table: ({ children }) => (
                              <div className="my-2 overflow-x-auto rounded-lg border border-stone-200">
                                <table className="min-w-full text-xs">{children}</table>
                              </div>
                            ),
                            thead: ({ children }) => <thead className="bg-stone-100">{children}</thead>,
                            tbody: ({ children }) => <tbody className="[&>tr:nth-child(even)]:bg-stone-50">{children}</tbody>,
                            th: ({ children }) => <th className="border-b border-stone-200 px-3 py-1.5 text-left font-semibold text-stone-700">{children}</th>,
                            td: ({ children }) => <td className="border-b border-stone-100 px-3 py-1.5 text-stone-600">{children}</td>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                        {/* Streaming cursor — pulsing dot */}
                        {msg.isStreaming && msg.content && (
                          <span className="ml-1 inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse-dot" />
                        )}
                        {msg.isStreaming && !msg.content && (
                          <span className="inline-flex items-center gap-1 text-stone-400">
                            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse-dot" />
                            <span className="text-xs">Thinking...</span>
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Bottom area — gradient fade + suggestions + floating input */}
      <div className="absolute bottom-0 left-0 right-0">
        {/* Gradient fade */}
        <div className="input-fade-bg h-8 pointer-events-none" />

        <div className="bg-[#f7f5f2] px-4 pb-4">
          {/* Follow-up suggestions */}
          {!isProcessing && messages.length > 0 && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.isStreaming && (
            <div className="mx-auto mb-3 flex max-w-3xl flex-wrap gap-2">
              {FOLLOWUP_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={isProcessing}
                  className="rounded-xl border border-stone-200 bg-white px-3 py-1.5 text-xs text-stone-500 shadow-sm transition-all hover:border-amber-300 hover:bg-amber-50/50 hover:-translate-y-0.5 disabled:opacity-40"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Floating input bar */}
          <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
            <div className="flex items-center gap-2 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-lg transition-all focus-within:border-amber-400 focus-within:ring-2 focus-within:ring-amber-400/20">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={hasReport ? "Ask about this property's zoning..." : "Enter an address or ask a question..."}
                disabled={isProcessing}
                className="flex-1 bg-transparent text-sm text-stone-800 placeholder-stone-400 outline-none"
              />
              <button
                type="submit"
                disabled={!input.trim() || isProcessing}
                aria-label="Send message"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-700 text-white transition-colors hover:bg-amber-600 disabled:opacity-30"
              >
                {isProcessing ? (
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
