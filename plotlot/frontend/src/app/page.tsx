"use client";

import { useState, useRef, useEffect, useCallback, FormEvent } from "react";
import { motion } from "framer-motion";
import { staggerContainer, staggerItem, fadeUp, springGentle } from "@/lib/motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TabbedReport from "@/components/TabbedReport";
import AnalysisStream from "@/components/AnalysisStream";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import ModeToggle from "@/components/ModeToggle";
import type { AppMode } from "@/components/ModeToggle";
import CapabilityChips from "@/components/CapabilityChips";
import ToolCards from "@/components/ToolCards";
import DocumentCanvas from "@/components/DocumentCanvas";
import ErrorBoundary from "@/components/ErrorBoundary";
import InputBar from "@/components/InputBar";
import ThinkingIndicator from "@/components/ThinkingIndicator";
import ZoningReport from "@/components/ZoningReport";
import {
  AnalysisError,
  PipelineStatus,
  ZoningReportData,
  ChatMessageData,
  ToolUseEvent,
  ThinkingEvent,
  streamAnalysis,
  streamChat,
  saveAnalysis,
} from "@/lib/api";
import {
  createSession as createLocalSession,
  getSession as getLocalSession,
  updateSession as updateLocalSession,
} from "@/lib/sessions";

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
  thinkingEvents?: ThinkingEvent[];
  report?: ZoningReportData;
  saveStatus?: "idle" | "saving" | "saved" | "error";
  toolActivity?: ToolActivity[];
  errorType?: "timeout" | "bad_address" | "backend_unavailable" | "generic";
  retryAddress?: string;
  reportVariant?: "lookup" | "agent";
}

// ---------------------------------------------------------------------------
// Address detection heuristic
// ---------------------------------------------------------------------------

const ADDRESS_PATTERN = /\d+\s+(?:\w+\s+)+(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ter|terrace|ct|court|ln|lane|way|pl|place|cir|circle|pkwy|parkway|hwy|highway|trl|trail|real|path)\b/i;
const ADDRESS_WITH_CITY_ZIP = /\d+\s+[\w\s]+,\s*[\w\s]+,\s*[A-Z]{2}\s+\d{5}/i;

function extractAddress(text: string): string | null {
  if (ADDRESS_PATTERN.test(text)) {
    return text.trim();
  }
  if (ADDRESS_WITH_CITY_ZIP.test(text)) {
    return text.trim();
  }
  if (/\b(analyze|look up|lookup|check|search|zoning (?:for|rules|regulations|code)|what can .* build)\b/i.test(text)) {
    // Only extract if there's an actual street address (starts with a number)
    const match = text.match(/\d+\s+[\w\s]+(?:,\s*[\w\s]+){0,3}/);
    if (match) return match[0].trim();
    // No street address found — route to chat instead
    return null;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Suggestions
// ---------------------------------------------------------------------------

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
  const [mode, setMode] = useState<AppMode>("lookup");
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentReport, setCurrentReport] = useState<ZoningReportData | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("plotlot_backend_session");
  });
  const [docCanvasOpen, setDocCanvasOpen] = useState(false);
  const [contextualSuggestions, setContextualSuggestions] = useState<string[]>([]);
  const [inputError, setInputError] = useState<string | null>(null);
  const [localSessionId, setLocalSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const localSessionIdRef = useRef<string | null>(null);
  const messagesRef = useRef<DisplayMessage[]>([]);
  const currentReportRef = useRef<ZoningReportData | null>(null);
  const modeRef = useRef<AppMode>("lookup");
  const hasProcessedRef = useRef(false);

  const makeMessageId = useCallback(() => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }, []);

  const normalizeMessageIds = useCallback(
    (msgs: DisplayMessage[]): DisplayMessage[] => {
      const seen = new Set<string>();
      return msgs.map((msg) => {
        const candidate = msg.id || makeMessageId();
        if (!seen.has(candidate)) {
          seen.add(candidate);
          return { ...msg, id: candidate };
        }
        let unique = makeMessageId();
        while (seen.has(unique)) unique = makeMessageId();
        seen.add(unique);
        return { ...msg, id: unique };
      });
    },
    [makeMessageId],
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Re-focus input on mount and when switching from welcome to conversation
  const isWelcome = messages.length === 0;
  useEffect(() => {
    inputRef.current?.focus();
  }, [isWelcome]);

  // Keep refs in sync with state
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  useEffect(() => { currentReportRef.current = currentReport; }, [currentReport]);
  useEffect(() => {
    modeRef.current = mode;
    window.dispatchEvent(new CustomEvent("plotlot:mode-changed", { detail: { mode } }));
  }, [mode]);
  useEffect(() => { localSessionIdRef.current = localSessionId; }, [localSessionId]);

  // Persist backend sessionId
  useEffect(() => {
    if (sessionId) localStorage.setItem("plotlot_backend_session", sessionId);
  }, [sessionId]);

  // Persist localSessionId
  useEffect(() => {
    if (localSessionId) localStorage.setItem("plotlot_last_session", localSessionId);
  }, [localSessionId]);

  // Mount: restore last session from localStorage
  useEffect(() => {
    const lastId = localStorage.getItem("plotlot_last_session");
    if (!lastId) return;
    const session = getLocalSession(lastId);
    if (!session || session.messages.length === 0) return;

    const restored: DisplayMessage[] = session.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ id: m.id, role: m.role as "user" | "assistant", content: m.content }));
    if (restored.length === 0) return;

    if (session.report && restored.length > 0) {
      const restoredReport = session.report;
      restored.splice(1, 0, {
        id: makeMessageId(),
        role: "system",
        content: "",
        report: restoredReport,
        reportVariant: session.mode,
      });
      queueMicrotask(() => setCurrentReport(restoredReport));
    }
    setMessages(normalizeMessageIds(restored));
    setLocalSessionId(lastId);
    localSessionIdRef.current = lastId;
  }, [makeMessageId, normalizeMessageIds]);

  // Save messages to local session after processing completes
  useEffect(() => {
    if (isProcessing) {
      hasProcessedRef.current = true;
      return;
    }
    if (!hasProcessedRef.current) return;
    hasProcessedRef.current = false;

    const msgs = messagesRef.current;
    const report = currentReportRef.current;
    const currentMode = modeRef.current;
    const sid = localSessionIdRef.current;

    const saveable = msgs
      .filter((m) => (m.role === "user" || m.role === "assistant") && m.content && !m.isStreaming)
      .map((m) => ({ id: m.id, role: m.role as "user" | "assistant", content: m.content, timestamp: new Date().toISOString() }));
    if (saveable.length === 0) return;

    const title = saveable[0]?.content?.slice(0, 60) || "New conversation";
    if (sid) {
      updateLocalSession(sid, { messages: saveable, ...(report ? { report } : {}) });
    } else {
      const newSession = createLocalSession(currentMode);
      updateLocalSession(newSession.id, { title, messages: saveable, ...(report ? { report } : {}) });
      setLocalSessionId(newSession.id);
      localSessionIdRef.current = newSession.id;
    }
    window.dispatchEvent(new CustomEvent("plotlot:sessions-changed"));
  }, [isProcessing]);

  // Listen for session selection from sidebar
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent<{ id: string }>).detail?.id;
      if (!id) return;
      const session = getLocalSession(id);
      if (!session) return;

      const restored: DisplayMessage[] = session.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ id: m.id, role: m.role as "user" | "assistant", content: m.content }));

      if (session.report && restored.length > 0) {
        restored.splice(1, 0, {
          id: makeMessageId(),
          role: "system",
          content: "",
          report: session.report,
          reportVariant: session.mode,
        });
        setCurrentReport(session.report);
      } else {
        setCurrentReport(null);
      }
      setMessages(normalizeMessageIds(restored));
      setLocalSessionId(id);
      localSessionIdRef.current = id;
      setInput("");
      setIsProcessing(false);
    };
    window.addEventListener("plotlot:session-selected", handler);
    return () => window.removeEventListener("plotlot:session-selected", handler);
  }, [makeMessageId, normalizeMessageIds]);

  const addMessage = useCallback((msg: Omit<DisplayMessage, "id">) => {
    const newMsg = { ...msg, id: makeMessageId() };
    setMessages((prev) => [...prev, newMsg]);
    return newMsg.id;
  }, [makeMessageId]);

  const updateMessage = useCallback((id: string, updates: Partial<DisplayMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    );
  }, []);

  // Run the full analysis pipeline
  const runAnalysis = useCallback(
    async (address: string, reportVariant: "lookup" | "agent", skipSteps: string[] = []) => {
      const progressId = addMessage({
        role: "system",
        content: "",
        pipelineSteps: [{
          step: "connecting",
          message: "Connecting to server...",
        }],
        thinkingEvents: [],
      });

      try {
        let finalReport: ZoningReportData | null = null;

        await streamAnalysis(
          {
            address,
            dealType: "land_deal",
            skipSteps,
          },
          (status) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== progressId) return m;
                let steps = m.pipelineSteps || [];
                // Mark "connecting" as complete when first real step arrives
                const connectingIdx = steps.findIndex((s) => s.step === "connecting" && !s.complete);
                if (connectingIdx >= 0 && status.step !== "connecting") {
                  steps = steps.map((s) =>
                    s.step === "connecting" ? { ...s, complete: true, message: "Connected" } : s,
                  );
                }
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
            updateMessage(progressId, {
              report,
              pipelineSteps: undefined,
              reportVariant,
            });
          },
          (error: AnalysisError) => {
            // Error recovery UX — provide actionable buttons based on error type
            const loweredError = error.detail.toLowerCase();
            const isTimeout = error.errorType === "timeout";
            const isBadAddress =
              error.errorType === "bad_address" ||
              error.errorType === "geocoding_failed" ||
              error.errorType === "low_accuracy" ||
              loweredError.includes("geocod") ||
              loweredError.includes("outside coverage") ||
              loweredError.includes("could not");
            const isBackendUnavailable =
              error.errorType === "backend_unavailable" ||
              loweredError.includes("backend is offline") ||
              loweredError.includes("temporarily unavailable");

            let errorContent = isBackendUnavailable
              ? "PlotLot's analysis backend is temporarily offline. Please try again shortly."
              : `I couldn't analyze that address: ${error.detail}`;
            if (isTimeout) {
              errorContent += "\n\nThe server took too long to respond. This can happen during the first request. Click **Retry** to try again.";
            } else if (isBadAddress) {
              errorContent += "\n\nPlease check the address and try a different one.";
            }
            updateMessage(progressId, {
              role: "assistant",
              content: errorContent,
              pipelineSteps: undefined,
              errorType: isTimeout ? "timeout" : isBadAddress ? "bad_address" : isBackendUnavailable ? "backend_unavailable" : "generic",
              retryAddress: address,
            } as Partial<DisplayMessage>);
          },
          (thinkingEvent) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== progressId) return m;
                return {
                  ...m,
                  thinkingEvents: [...(m.thinkingEvents || []), thinkingEvent],
                };
              }),
            );
          },
          (suggestions) => {
            setContextualSuggestions(suggestions);
          },
        );

        if (finalReport && mode === "agent") {
          addMessage({
            role: "assistant",
            content: "Here's the full zoning analysis. Ask me anything about this property.",
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

      const address = extractAddress(text);

      // Lookup mode: validate address BEFORE adding to chat
      if (mode === "lookup" && !address) {
        setInputError("Please enter a street address to run a lookup analysis");
        return;
      }

      setIsProcessing(true);
      setInput("");
      setInputError(null);

      addMessage({ role: "user", content: text.trim() });

      // Lookup mode: address → direct analysis
      if (mode === "lookup" && address) {
        setCurrentReport(null);
        await runAnalysis(address, "lookup");
        setIsProcessing(false);
        return;
      }

      // Agent mode: address detected — run pipeline directly
      if (address && !currentReport) {
        await runAnalysis(address, "agent");
        setIsProcessing(false);
        return;
      }
      if (address && currentReport) {
        setCurrentReport(null);
        await runAnalysis(address, "agent");
        setIsProcessing(false);
        return;
      }

      // Regular chat (agent mode only)
      const assistantId = addMessage({
        role: "assistant",
        content: "",
        isStreaming: true,
        toolActivity: [],
        thinkingEvents: [],
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
            window.dispatchEvent(new CustomEvent("plotlot:sessions-changed"));
          },
          (toolEvent: ToolUseEvent) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const tools = m.toolActivity || [];
                const lastTool = tools[tools.length - 1];
                if (lastTool?.tool === toolEvent.tool && lastTool.message === toolEvent.message) {
                  return m;
                }
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
                const tools = [...(m.toolActivity || [])];
                for (let i = tools.length - 1; i >= 0; i -= 1) {
                  if (tools[i].tool === toolName && tools[i].status === "running") {
                    tools[i] = { ...tools[i], status: "complete" as const };
                    break;
                  }
                }
                return { ...m, toolActivity: tools };
              }),
            );
          },
          (thinkingEvent: ThinkingEvent) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                return {
                  ...m,
                  thinkingEvents: [...(m.thinkingEvents || []), thinkingEvent],
                };
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
    [messages, isProcessing, currentReport, sessionId, mode, addMessage, updateMessage, runAnalysis],
  );

  const handleModeChange = useCallback((nextMode: AppMode) => {
    setMode(nextMode);
    setContextualSuggestions([]);
    setInputError(null);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const nextMode = (event as CustomEvent<{ mode?: AppMode }>).detail?.mode;
      if (!nextMode) return;
      if (nextMode !== modeRef.current) {
        setMode(nextMode);
        setContextualSuggestions([]);
        setInputError(null);
      }
      setTimeout(() => inputRef.current?.focus(), 50);
    };
    window.addEventListener("plotlot:mode-change", handler);
    return () => window.removeEventListener("plotlot:mode-change", handler);
  }, []);

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

  const handleNewAnalysis = useCallback(() => {
    setMessages([]);
    setCurrentReport(null);
    setSessionId(null);
    setLocalSessionId(null);
    localSessionIdRef.current = null;
    hasProcessedRef.current = false;
    setContextualSuggestions([]);
    setInput("");
    setIsProcessing(false);
    localStorage.removeItem("plotlot_backend_session");
    localStorage.removeItem("plotlot_last_session");
    window.dispatchEvent(new CustomEvent("plotlot:clear-active-session"));
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // Mode toggle is now the imported ModeToggle component

  // ─── Welcome State (both modes) ────────────────────────────────────
  if (isWelcome) {
    return (
      <main className="relative flex min-h-screen w-full max-w-full items-center justify-center overflow-x-hidden bg-[#f5f5f6] px-4 py-8 sm:px-6 lg:px-10">
        {mode === "agent" && (
          <div className="absolute top-6 left-1/2 -translate-x-1/2 rounded-full border border-[#d8e4ff] bg-[#eaf1ff] px-4 py-1.5 text-sm font-medium text-[#3b82f6]">
            ♫ Upgrade your plan
          </div>
        )}

        <div className="mx-auto flex w-full max-w-[1040px] flex-col items-center">
          <motion.div
            className="mb-8 w-full text-center"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            <div className="mx-auto flex max-w-[780px] flex-col items-center">
              <motion.div
                variants={staggerItem}
                className="mb-4 flex items-center justify-center gap-2 text-sm tracking-wide text-[var(--text-muted)]"
              >
                <span className="text-[var(--brand)]">✦</span>
                <span>Hi there</span>
              </motion.div>

              {mode === "agent" && (
                <motion.p variants={staggerItem} className="mb-3 text-[72px] font-black tracking-[0.18em] text-[#111827]">
                  PLOTLOT
                </motion.p>
              )}

              <motion.h1
                variants={staggerItem}
                className="max-w-[700px] text-center font-display text-[clamp(3.0rem,4.8vw,4.1rem)] leading-[1.02] text-[var(--text-primary)]"
              >
                {mode === "lookup" ? (
                  <>Analyze any property<br />in the US</>
                ) : (
                  <>Ask anything about zoning &amp; land</>
                )}
              </motion.h1>

              <motion.p variants={staggerItem} className="mt-4 max-w-2xl text-center text-[15px] leading-7 text-[var(--text-muted)] sm:text-base">
                {mode === "lookup"
                  ? "Zoning, density, comps, pro forma, and development potential — in seconds"
                  : "Use the consultant harness: run analyses, attach evidence, and generate defensible reports in one workspace."}
              </motion.p>
            </div>
          </motion.div>

          <motion.form
            onSubmit={handleSubmit}
            {...fadeUp}
            transition={{ ...springGentle, delay: 0.2 }}
            className="relative z-30 mb-6 w-full max-w-[980px] self-center"
          >
            <div
              className="glass-panel flex min-h-[76px] items-center gap-2 rounded-[34px] border border-[#cfd5df] bg-white px-4 py-3 transition-all focus-within:border-[#94a3b8] focus-within:ring-2 focus-within:ring-[#e2e8f0] sm:px-5"
              style={{ boxShadow: "0 1px 2px rgba(0,0,0,0.06)" }}
            >
              {mode === "lookup" ? (
                <AddressAutocomplete
                  inputRef={inputRef}
                  value={input}
                  onChange={(v) => { setInput(v); if (inputError) setInputError(null); }}
                  onSelect={(address) => sendMessage(address)}
                  placeholder="Enter a property address..."
                  disabled={isProcessing}
                />
              ) : (
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => { setInput(e.target.value); if (inputError) setInputError(null); }}
                  placeholder="Ask about zoning, density, or property data..."
                  disabled={isProcessing}
                  className="min-w-0 flex-1 bg-transparent text-lg text-[#374151] placeholder:text-[#9ca3af] focus:outline-none"
                  data-testid="agent-input"
                />
              )}
              <ModeToggle mode={mode} onChange={handleModeChange} />
              <button
                type="submit"
                disabled={!input.trim() || isProcessing}
                aria-label="Send message"
                data-testid="send-button"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#111827] text-white transition-all hover:opacity-90 disabled:opacity-20"
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
            {inputError && <p className="mt-2 px-1 text-xs text-red-500">{inputError}</p>}
          </motion.form>

          <motion.div
            {...fadeUp}
            transition={{ ...springGentle, delay: 0.3 }}
            className="relative z-0 min-h-[72px] w-full max-w-[980px] self-center"
          >
            {mode === "lookup" ? (
              <CapabilityChips mode={mode} onSelect={sendMessage} disabled={isProcessing} />
            ) : (
              <ToolCards
                onAnalyze={() => inputRef.current?.focus()}
                onGenerateDoc={() => setDocCanvasOpen(true)}
                onSendPrompt={sendMessage}
                disabled={isProcessing}
                hasReport={!!currentReport}
                county={currentReport?.county}
              />
            )}
          </motion.div>

          <motion.p
            {...fadeUp}
            transition={{ ...springGentle, delay: 0.4 }}
            className="mt-10 text-center text-xs text-[var(--text-muted)]"
          >
            PlotLot analyzes zoning, density, comps &amp; pro forma for any US property
          </motion.p>
        </div>
      </main>
    );
  }

// ─── Conversation State ───────────────────────────────────────────────
  return (
    <div className="relative flex h-[calc(100vh-4rem)] flex-col bg-[#f5f5f6]">
      {mode === "agent" && (
        <div className="pointer-events-none fixed left-1/2 top-5 z-40 -translate-x-1/2 rounded-full border border-[#d8e4ff] bg-[#eaf1ff] px-4 py-1.5 text-sm font-medium text-[#3b82f6]">
          ♫ Upgrade your plan
        </div>
      )}
      {/* New Analysis button — fixed top-right */}
      <div className="fixed right-4 top-5 z-40 sm:right-6">
        <button
          onClick={handleNewAnalysis}
          data-testid="new-analysis-button"
          className="shrink-0 flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] transition-all hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)] active:scale-[0.98]"
          style={{ boxShadow: "var(--shadow-nav)" }}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" />
          </svg>
          New analysis
        </button>
      </div>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto pb-52">
        <div className="mx-auto max-w-3xl space-y-4 px-3 py-4 sm:space-y-6 sm:px-4 sm:py-6" role="log" aria-live="polite" aria-label="Analysis conversation">
          {messages.map((msg) => (
            <div key={msg.id} className="animate-fade-up">
              {/* Pipeline progress — inline stepper */}
              {msg.pipelineSteps && msg.pipelineSteps.length > 0 && !msg.report && (
                <div className="flex items-start gap-3">
                  <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-xs font-black text-white">
                    P
                  </div>
                  <AnalysisStream
                    steps={msg.pipelineSteps}
                    error={null}
                    onWrongProperty={handleNewAnalysis}
                    thinkingEvents={msg.thinkingEvents}
                  />
                </div>
              )}

              {/* Embedded report — use the same polished report shell in both lookup and agent flows */}
              {msg.report && (
                <div className="space-y-3 animate-fade-up">
                  <ErrorBoundary>
                    {msg.reportVariant === "lookup" ? (
                      <TabbedReport report={msg.report} dealType="land_deal" />
                    ) : (
                      <ZoningReport report={msg.report} />
                    )}
                  </ErrorBoundary>
                  {msg.report.confidence_warning && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-950/40">
                      <div className="flex items-start gap-3">
                        <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                        </svg>
                        <div>
                          <p className="text-sm font-medium text-amber-800 dark:text-amber-400">{msg.report.confidence_warning}</p>
                          {msg.report.suggested_next_steps && msg.report.suggested_next_steps.length > 0 && (
                            <ul className="mt-1.5 space-y-1">
                              {msg.report.suggested_next_steps.map((step, i) => (
                                <li key={i} className="text-xs text-amber-700 dark:text-amber-500">&#8226; {step}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setDocCanvasOpen(true)}
                      className="min-h-[44px] rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-400 dark:hover:bg-amber-950/50 sm:min-h-0 sm:py-1.5"
                    >
                      Generate Documents
                    </button>
                    <button
                      onClick={() => handleSave(msg.id, msg.report!)}
                      disabled={msg.saveStatus === "saving" || msg.saveStatus === "saved"}
                      className={`min-h-[44px] rounded-lg px-4 py-2 text-sm font-semibold transition-colors sm:min-h-0 sm:py-1.5 ${
                        msg.saveStatus === "saved"
                          ? "bg-lime-100 text-lime-700"
                          : msg.saveStatus === "error"
                            ? "bg-red-100 text-red-600"
                            : "border border-[var(--border)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-raised)]"
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

              {msg.role === "assistant" && msg.thinkingEvents && msg.thinkingEvents.length > 0 && (
                <div className="mb-2 ml-9 max-w-[95%] sm:max-w-[85%]">
                  <ThinkingIndicator events={msg.thinkingEvents} />
                </div>
              )}

              {/* Tool use badges (ChatGPT-style) */}
              {msg.toolActivity && msg.toolActivity.length > 0 && (() => {
                const visibleTools = msg.thinkingEvents && msg.thinkingEvents.length > 0
                  ? msg.toolActivity.filter((t) => t.status === "running").slice(-1)
                  : msg.toolActivity;

                if (visibleTools.length === 0) return null;

                return (
                  <div className="mb-2 flex justify-start">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-xs font-black text-white">
                        P
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {visibleTools.map((t, i) => (
                          <span
                            key={i}
                            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                              t.status === "running"
                                ? "border border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                                : "border border-[var(--border)] bg-[var(--bg-surface-raised)] text-[var(--text-muted)]"
                            }`}
                          >
                            {t.status === "running" ? (
                              <div className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse-dot" />
                            ) : (
                              <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                              </svg>
                            )}
                            {t.message}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Regular message */}
              {msg.content && msg.role !== "system" && (
                <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "user" ? (
                    /* User message — right-aligned plain text, no bubble */
                    <div className="max-w-[90%] text-sm leading-relaxed text-[var(--text-secondary)] sm:max-w-[75%]">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant message — left-aligned with avatar */
                    <div className="flex items-start gap-2 max-w-[95%] sm:gap-3 sm:max-w-[85%]">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-xs font-black text-white">
                        P
                      </div>
                      <div
                        className="text-sm leading-relaxed text-[var(--text-secondary)] min-w-0"
                        data-testid={
                          msg.errorType ||
                          msg.content.startsWith("Error:") ||
                          msg.content.startsWith("Connection error:")
                            ? "report-error"
                            : undefined
                        }
                      >
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            strong: ({ children }) => <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>,
                            ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
                            li: ({ children }) => <li>{children}</li>,
                            h1: ({ children }) => <h1 className="mb-2 text-lg font-bold text-[var(--text-primary)]">{children}</h1>,
                            h2: ({ children }) => <h2 className="mb-2 text-base font-bold text-[var(--text-primary)]">{children}</h2>,
                            h3: ({ children }) => <h3 className="mb-1 text-sm font-bold text-[var(--text-primary)]">{children}</h3>,
                            a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-amber-700 underline hover:text-amber-600">{children}</a>,
                            code: ({ children }) => <code className="rounded bg-[var(--bg-surface-raised)] px-1.5 py-0.5 text-xs font-mono text-[var(--text-secondary)]">{children}</code>,
                            pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded-lg bg-[var(--bg-surface-raised)] p-3 text-xs">{children}</pre>,
                            table: ({ children }) => (
                              <div className="my-2 overflow-x-auto rounded-lg border border-[var(--border)]">
                                <table className="min-w-full text-xs">{children}</table>
                              </div>
                            ),
                            thead: ({ children }) => <thead className="bg-[var(--bg-surface-raised)]">{children}</thead>,
                            tbody: ({ children }) => <tbody className="[&>tr:nth-child(even)]:bg-[var(--bg-surface-raised)]">{children}</tbody>,
                            th: ({ children }) => <th className="border-b border-[var(--border)] px-3 py-1.5 text-left font-semibold text-[var(--text-secondary)]">{children}</th>,
                            td: ({ children }) => <td className="border-b border-[var(--border)] px-3 py-1.5 text-[var(--text-secondary)]">{children}</td>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                        {/* Streaming cursor — pulsing dot */}
                        {msg.isStreaming && msg.content && (
                          <span className="ml-1 inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse-dot" />
                        )}
                        {msg.isStreaming && !msg.content && (
                          <span className="inline-flex items-center gap-1 text-[var(--text-muted)]">
                            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse-dot" />
                            <span className="text-xs">Thinking...</span>
                          </span>
                        )}
                        {/* Error recovery buttons */}
                        {msg.errorType && !msg.isStreaming && (
                          <div className="mt-3 flex gap-2">
                            {(msg.errorType === "timeout" || msg.errorType === "backend_unavailable") && msg.retryAddress && (
                              <button
                                onClick={() => {
                                  setMessages((prev) => prev.filter((m) => m.id !== msg.id));
                                  runAnalysis(msg.retryAddress!, msg.reportVariant ?? "lookup");
                                }}
                                disabled={isProcessing}
                                data-testid="report-retry-button"
                                className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100 disabled:opacity-40"
                              >
                                Retry
                              </button>
                            )}
                            {msg.errorType === "bad_address" && (
                              <button
                                onClick={() => {
                                  setInput("");
                                  inputRef.current?.focus();
                                }}
                                className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface-raised)]"
                              >
                                Try another address
                              </button>
                            )}
                          </div>
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

        <div className="bg-[var(--bg-primary)] px-3 pb-3 sm:px-4 sm:pb-4">
          {/* Contextual suggestions — lookup mode after report */}
          {mode === "lookup" && hasReport && contextualSuggestions.length > 0 && !isProcessing && (
            <div className="mx-auto mb-3 flex max-w-3xl flex-wrap gap-2 px-3 sm:gap-2 sm:px-0">
              {contextualSuggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => { handleModeChange("agent"); sendMessage(s); }}
                  className="min-h-[44px] rounded-full border border-amber-200 bg-amber-50/50 px-4 py-2 text-xs text-amber-700 transition-all hover:bg-amber-100 hover:-translate-y-0.5 active:scale-[0.98] dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400 dark:hover:bg-amber-950/50 sm:min-h-0 sm:py-1.5"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Follow-up suggestions — agent mode only */}
          {mode === "agent" && !isProcessing && messages.length > 0 && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.isStreaming && (
            <div className="mx-auto mb-3 flex max-w-3xl flex-wrap gap-2 px-3 sm:gap-2 sm:px-0">
              {FOLLOWUP_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={isProcessing}
                  className="min-h-[44px] rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-2 text-xs text-[var(--text-muted)] transition-all hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)] hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-40 sm:min-h-0 sm:py-1.5"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input bar */}
          <div>
            <InputBar
              inputRef={inputRef}
              value={input}
              onChange={(v) => { setInput(v); if (inputError) setInputError(null); }}
              onSubmit={handleSubmit}
              onAddressSelect={(address) => sendMessage(address)}
              mode={mode}
              onModeChange={handleModeChange}
              placeholder={mode === "lookup"
                ? "Enter a property address..."
                : hasReport
                  ? "Ask about this property's zoning..."
                  : "Ask about zoning, density, or property data..."
              }
              disabled={isProcessing}
              isProcessing={isProcessing}
            />
            {inputError && (
              <p className="mt-2 px-4 text-xs text-red-500">{inputError}</p>
            )}
          </div>

        </div>
      </div>

      {/* Document Canvas modal */}
      {currentReport && (
        <DocumentCanvas
          report={currentReport}
          isOpen={docCanvasOpen}
          onClose={() => setDocCanvasOpen(false)}
        />
      )}
    </div>
  );
}
