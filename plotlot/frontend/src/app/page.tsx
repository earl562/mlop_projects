"use client";

import { useState, useRef, useEffect, useCallback, FormEvent, useId } from "react";
import { motion } from "framer-motion";
import { staggerContainer, staggerItem, fadeUp, springGentle } from "@/lib/motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ZoningReport from "@/components/ZoningReport";
import TabbedReport from "@/components/TabbedReport";
import DealTypeSelector from "@/components/DealTypeSelector";
import type { DealType } from "@/components/DealTypeSelector";
import PipelineApproval from "@/components/PipelineApproval";
import AnalysisStream from "@/components/AnalysisStream";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import ModeToggle from "@/components/ModeToggle";
import type { AppMode } from "@/components/ModeToggle";
import CapabilityChips from "@/components/CapabilityChips";
import ToolCards from "@/components/ToolCards";
import DocumentCanvas from "@/components/DocumentCanvas";
import ErrorBoundary from "@/components/ErrorBoundary";
import InputBar from "@/components/InputBar";
import {
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
  errorType?: "timeout" | "bad_address" | "generic";
  retryAddress?: string;
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
  const [sessionId, setSessionId] = useState<string | null>(null);
  // Lookup mode: deal type flow
  const [pendingAddress, setPendingAddress] = useState<string | null>(null);
  const [selectedDealType, setSelectedDealType] = useState<DealType | null>(null);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [docCanvasOpen, setDocCanvasOpen] = useState(false);
  const [contextualSuggestions, setContextualSuggestions] = useState<string[]>([]);
  const [inputError, setInputError] = useState<string | null>(null);
  const [localSessionId, setLocalSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const idPrefix = useId();
  const msgCounterRef = useRef(0);
  const localSessionIdRef = useRef<string | null>(null);
  const messagesRef = useRef<DisplayMessage[]>([]);
  const currentReportRef = useRef<ZoningReportData | null>(null);
  const modeRef = useRef<AppMode>("lookup");
  const hasProcessedRef = useRef(false);

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
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { localSessionIdRef.current = localSessionId; }, [localSessionId]);

  // Fix 3: Mode switch — clear lookup-mode state
  useEffect(() => {
    setPendingAddress(null);
    setSelectedDealType(null);
    setAwaitingApproval(false);
    setContextualSuggestions([]);
  }, [mode]);

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
    const backendId = localStorage.getItem("plotlot_backend_session");
    if (backendId) setSessionId(backendId);

    const lastId = localStorage.getItem("plotlot_last_session");
    if (!lastId) return;
    const session = getLocalSession(lastId);
    if (!session || session.messages.length === 0) return;

    const restored: DisplayMessage[] = session.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ id: m.id, role: m.role as "user" | "assistant", content: m.content }));
    if (restored.length === 0) return;

    if (session.report && restored.length > 0) {
      restored.splice(1, 0, {
        id: `${idPrefix}-mount-report`,
        role: "system",
        content: "",
        report: session.report,
      });
      setCurrentReport(session.report);
    }
    setMessages(restored);
    setLocalSessionId(lastId);
    localSessionIdRef.current = lastId;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          id: `${idPrefix}-sel-report`,
          role: "system",
          content: "",
          report: session.report,
        });
        setCurrentReport(session.report);
      } else {
        setCurrentReport(null);
      }
      setMessages(restored);
      setLocalSessionId(id);
      localSessionIdRef.current = id;
      setInput("");
      setPendingAddress(null);
      setSelectedDealType(null);
      setAwaitingApproval(false);
      setIsProcessing(false);
    };
    window.addEventListener("plotlot:session-selected", handler);
    return () => window.removeEventListener("plotlot:session-selected", handler);
  }, [idPrefix]);

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
    async (address: string, skipSteps: string[] = []) => {
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
            dealType: selectedDealType || "land_deal",
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
            updateMessage(progressId, { report, pipelineSteps: undefined });
          },
          (error) => {
            // Error recovery UX — provide actionable buttons based on error type
            const isTimeout = error.toLowerCase().includes("timeout") || error.toLowerCase().includes("timed out");
            const isBadAddress = error.toLowerCase().includes("geocod") || error.toLowerCase().includes("outside coverage") || error.toLowerCase().includes("could not");
            let errorContent = `I couldn't analyze that address: ${error}`;
            if (isTimeout) {
              errorContent += "\n\nThe server took too long to respond. This can happen during the first request. Click **Retry** to try again.";
            } else if (isBadAddress) {
              errorContent += "\n\nPlease check the address and try a different one.";
            }
            updateMessage(progressId, {
              role: "assistant",
              content: errorContent,
              pipelineSteps: undefined,
              errorType: isTimeout ? "timeout" : isBadAddress ? "bad_address" : "generic",
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

        if (finalReport) {
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
    [addMessage, updateMessage, selectedDealType],
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

      // Lookup mode: address → deal type selector → pipeline
      if (mode === "lookup" && address) {
        setPendingAddress(address);
        setSelectedDealType(null);
        setCurrentReport(null);
        setIsProcessing(false);
        return;
      }

      // Agent mode: address detected — run pipeline directly
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

      // Regular chat (agent mode only)
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
            window.dispatchEvent(new CustomEvent("plotlot:sessions-changed"));
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
    [messages, isProcessing, currentReport, sessionId, mode, addMessage, updateMessage, runAnalysis],
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

  // Handle deal type selection in lookup mode — show pipeline approval
  const handleDealTypeSelect = useCallback(
    (dealType: DealType) => {
      if (!pendingAddress) return;
      setSelectedDealType(dealType);
      setAwaitingApproval(true);
    },
    [pendingAddress],
  );

  // Handle pipeline approval — run with selected skip steps
  const handlePipelineApprove = useCallback(
    async (skipSteps: string[]) => {
      if (!pendingAddress) return;
      const address = pendingAddress;
      setAwaitingApproval(false);
      setPendingAddress(null);
      setIsProcessing(true);
      try {
        await runAnalysis(address, skipSteps);
      } finally {
        setIsProcessing(false);
      }
    },
    [pendingAddress, runAnalysis],
  );

  const handlePipelineCancel = useCallback(() => {
    setAwaitingApproval(false);
    setSelectedDealType(null);
  }, []);

  const handleNewAnalysis = useCallback(() => {
    setMessages([]);
    setCurrentReport(null);
    setSessionId(null);
    setLocalSessionId(null);
    localSessionIdRef.current = null;
    hasProcessedRef.current = false;
    setPendingAddress(null);
    setSelectedDealType(null);
    setAwaitingApproval(false);
    setInput("");
    setIsProcessing(false);
    localStorage.removeItem("plotlot_backend_session");
    localStorage.removeItem("plotlot_last_session");
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // Mode toggle is now the imported ModeToggle component

  // ─── Welcome State (both modes) ────────────────────────────────────
  if (isWelcome) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center px-4 pt-[15vh] sm:px-6">
        {/* Greeting */}
        <motion.div
          className="mb-10 text-center sm:mb-14"
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={staggerItem} className="mb-4 flex items-center justify-center gap-2">
            <svg className="h-4 w-4 text-amber-500/70" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 2L12.5 7.5L18 10L12.5 12.5L10 18L7.5 12.5L2 10L7.5 7.5L10 2Z" clipRule="evenodd" />
            </svg>
            <span className="text-sm tracking-wide text-[var(--text-muted)]">Hi there</span>
          </motion.div>
          <motion.h1
            variants={staggerItem}
            className="font-display text-4xl leading-tight text-[var(--text-primary)] sm:text-6xl sm:leading-[1.1]"
          >
            Analyze any property<br className="hidden sm:block" /> in the US
          </motion.h1>
          <motion.p variants={staggerItem} className="mt-4 text-sm text-[var(--text-muted)] sm:text-base">
            Zoning, density, comps, pro forma, and development potential — in seconds
          </motion.p>
        </motion.div>

        {/* Input bar — z-30 so autocomplete dropdown (z-50 inside) paints above chips below */}
        <motion.form
          onSubmit={handleSubmit}
          {...fadeUp}
          transition={{ ...springGentle, delay: 0.25 }}
          className="relative z-30 mb-6 w-full max-w-xl sm:mb-8"
        >
          <div
            className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 transition-all focus-within:border-amber-400/60 focus-within:ring-2 focus-within:ring-amber-400/15 sm:px-5 sm:py-3.5"
            style={{ boxShadow: "var(--shadow-elevated)" }}
          >
            <AddressAutocomplete
              inputRef={inputRef}
              value={input}
              onChange={(v) => { setInput(v); if (inputError) setInputError(null); }}
              onSelect={(address) => sendMessage(address)}
              placeholder={mode === "lookup" ? "Enter a property address..." : "Enter an address or ask a question..."}
              disabled={isProcessing}
            />
            <ModeToggle mode={mode} onChange={setMode} />
            <button
              type="submit"
              disabled={!input.trim() || isProcessing}
              aria-label="Send message"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--bg-primary)] transition-all hover:opacity-80 disabled:opacity-20 sm:h-9 sm:w-9"
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
          {inputError && (
            <p className="mt-2 px-1 text-xs text-red-500">{inputError}</p>
          )}
        </motion.form>

        {/* Capability chips / Tool cards — z-0 so autocomplete dropdown from form above paints on top */}
        <motion.div
          {...fadeUp}
          transition={{ ...springGentle, delay: 0.35 }}
          className="relative z-0 min-h-[72px] w-full max-w-xl"
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

        {/* Footer */}
        <motion.p
          {...fadeUp}
          transition={{ ...springGentle, delay: 0.45 }}
          className="mt-16 text-center text-xs text-[var(--text-muted)]"
        >
          PlotLot analyzes zoning, density, comps &amp; pro forma for any US property
        </motion.p>
      </div>
    );
  }

  // ─── Conversation State ───────────────────────────────────────────────
  return (
    <div className="relative flex h-[calc(100vh-4rem)] flex-col">
      {/* New Analysis button — fixed top-right */}
      <div className="fixed right-4 top-5 z-40 sm:right-6">
        <button
          onClick={handleNewAnalysis}
          className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] transition-all hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)] active:scale-[0.98]"
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

              {/* Embedded report — TabbedReport for lookup mode, ZoningReport for agent */}
              {msg.report && (
                <div className="space-y-3 animate-fade-up">
                  <ErrorBoundary>
                    {selectedDealType ? (
                      <TabbedReport report={msg.report} dealType={selectedDealType} />
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

              {/* Tool use badges (ChatGPT-style) */}
              {msg.toolActivity && msg.toolActivity.length > 0 && (
                <div className="mb-2 flex justify-start">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-xs font-black text-white">
                      P
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.toolActivity.map((t, i) => (
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
                          {t.status === "complete" ? `Used ${t.tool}` : t.message}
                        </span>
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
                    <div className="max-w-[90%] text-sm leading-relaxed text-[var(--text-secondary)] sm:max-w-[75%]">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant message — left-aligned with avatar */
                    <div className="flex items-start gap-2 max-w-[95%] sm:gap-3 sm:max-w-[85%]">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-800 text-xs font-black text-white">
                        P
                      </div>
                      <div className="text-sm leading-relaxed text-[var(--text-secondary)] min-w-0">
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
                            {msg.errorType === "timeout" && msg.retryAddress && (
                              <button
                                onClick={() => {
                                  setMessages((prev) => prev.filter((m) => m.id !== msg.id));
                                  runAnalysis(msg.retryAddress!);
                                }}
                                disabled={isProcessing}
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
          {/* Deal type selector — appears when address entered in lookup mode */}
          {pendingAddress && !selectedDealType && (
            <div className="mx-auto max-w-xl px-3 py-4 sm:px-0">
              <DealTypeSelector onSelect={handleDealTypeSelect} disabled={isProcessing} />
            </div>
          )}

          {/* Pipeline approval gate — appears after deal type selection */}
          {pendingAddress && selectedDealType && awaitingApproval && (
            <div className="mx-auto max-w-xl px-3 py-4 sm:px-0 animate-fade-up">
              <PipelineApproval
                address={pendingAddress}
                dealType={selectedDealType}
                onApprove={handlePipelineApprove}
                onCancel={handlePipelineCancel}
                disabled={isProcessing}
              />
            </div>
          )}

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
                  onClick={() => { setMode("agent"); sendMessage(s); }}
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

          {/* Input bar — hidden in lookup mode after report is shown */}
          {!(mode === "lookup" && hasReport) && (
            <div>
              <InputBar
                inputRef={inputRef}
                value={input}
                onChange={(v) => { setInput(v); if (inputError) setInputError(null); }}
                onSubmit={handleSubmit}
                onAddressSelect={(address) => sendMessage(address)}
                mode={mode}
                onModeChange={setMode}
                placeholder={hasReport ? "Ask about this property's zoning..." : "Enter an address or ask a question..."}
                disabled={isProcessing || !!pendingAddress || awaitingApproval}
                isProcessing={isProcessing}
              />
              {inputError && (
                <p className="mt-2 px-4 text-xs text-red-500">{inputError}</p>
              )}
            </div>
          )}

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
