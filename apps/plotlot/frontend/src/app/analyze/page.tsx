"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type AgentTaskEvent,
  type AgentTaskStatus,
  type BrowserActionEvent,
  type ReasoningEvent,
  streamChat,
  type ChatMessageData,
  type ThinkingEvent,
  type ToolUseEvent,
  type ToolResultEvent,
} from "../../lib/api";

type ToolActivity = {
  id: string;
  tool: string;
  message: string;
  status: "running" | "complete" | "error" | "blocked";
};

type ConsoleMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolActivity?: ToolActivity[];
  thinking?: ThinkingEvent[];
  isStreaming?: boolean;
};

type RunEvent = {
  id: string;
  kind: "turn" | "thinking" | "tool" | "evidence" | "risk" | "done" | "error";
  title: string;
  detail: string;
  status: "queued" | "running" | "complete" | "attention";
  createdAt: number;
};

type AgentTask = {
  id: string;
  type: string;
  title: string;
  detail: string;
  status: AgentTaskStatus;
  percent?: number;
  durationMs?: number;
  url?: string | null;
  screenshotB64?: string | null;
  citations?: string[];
  createdAt: number;
};

type AgentSession = {
  id: string;
  title: string;
  subtitle: string;
  updatedAt: number;
  backendSessionId: string | null;
  messages: ConsoleMessage[];
  events: RunEvent[];
  tasks: AgentTask[];
  browserActions: BrowserActionEvent[];
};

const STORAGE_KEY = "plotlot_agentic_sessions_v1";

const suggestions = [
  "Can this site support more units?",
  "Compare duplex, ADU, and rezoning paths",
  "Draft a consultant-style zoning memo",
  "What evidence would an underwriter need?",
];

const riskSignals = [
  "Overlay districts",
  "Parking burden",
  "Conditional-use triggers",
  "Human review threshold",
];

const analyzePlan = [
  {
    label: "Scope the site",
    description: "Anchor the parcel, district, or scenario before deeper reasoning starts.",
  },
  {
    label: "Gather evidence",
    description: "Pull ordinance, parcel, and tool-backed context into the turn.",
  },
  {
    label: "Synthesize the answer",
    description: "Convert observations into a concise consultant-style recommendation.",
  },
  {
    label: "Drive the next action",
    description: "Queue the next evidence ask, memo draft, or scenario follow-up.",
  },
] as const;

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toolLabel(tool: string) {
  return tool.replaceAll("_", " ");
}

function toolMode(tool: string) {
  const normalized = tool.toLowerCase();
  if (normalized.includes("ordinance") || normalized.includes("zoning")) return "ordinance";
  if (
    normalized.includes("browser") ||
    normalized.includes("browse") ||
    normalized.includes("web") ||
    normalized.includes("url") ||
    normalized.includes("search")
  ) {
    return "browser";
  }
  if (normalized.includes("document")) return "document";
  if (normalized.includes("spreadsheet") || normalized.includes("sheet")) return "spreadsheet";
  if (normalized.includes("property") || normalized.includes("parcel")) return "property";
  return "tool";
}

function computerActionLabel(activity: ToolActivity | undefined) {
  if (!activity) return "Standing by for browser, source, and ordinance work";
  const mode = toolMode(activity.tool);
  if (mode === "browser") return "Browsing source material";
  if (mode === "ordinance") return "Searching ordinance context";
  if (mode === "property") return "Reading parcel records";
  if (mode === "document") return "Preparing document output";
  if (mode === "spreadsheet") return "Preparing spreadsheet output";
  return `Running ${toolLabel(activity.tool)}`;
}

function taskTitleFromEvent(eventData: AgentTaskEvent) {
  return eventData.title || eventData.name || "Agent task";
}

function taskDetailFromEvent(eventData: AgentTaskEvent) {
  return eventData.detail || "PlotLot is executing a structured work step.";
}

function browserActionTitle(action: BrowserActionEvent | undefined) {
  if (!action) return "No browser action yet";
  const verb = action.action || action.type?.replace("browser_", "") || "browser";
  if (action.url) return `${verb}: ${action.url}`;
  if (action.selector) return `${verb}: ${action.selector}`;
  return verb;
}

function reasoningToThinking(eventData: ReasoningEvent): ThinkingEvent {
  const thought =
    eventData.summary ||
    eventData.thoughts?.join(" ") ||
    "Reasoning through the current land-use task.";
  return {
    step: eventData.phase || eventData.step || "reasoning",
    thoughts: eventData.alternatives?.length
      ? [`${thought} Alternatives considered: ${eventData.alternatives.join("; ")}`]
      : [thought],
  };
}

function createWelcomeMessage(): ConsoleMessage {
  return {
    id: "welcome",
    role: "assistant",
    content:
      "Bring me an address, parcel, zoning district, or development idea. I will reason through the land-use path, surface the source trail, and separate facts from open questions.",
  };
}

function createInitialSession(): AgentSession {
  const now = Date.now();
  return {
    id: createId("session"),
    title: "Land-use feasibility",
    subtitle: "New site analysis",
    updatedAt: now,
    backendSessionId: null,
    messages: [createWelcomeMessage()],
    tasks: [],
    browserActions: [],
    events: [
      {
        id: createId("event"),
        kind: "turn",
        title: "Workspace ready",
        detail: "PlotLot agent session initialized for zoning and feasibility review.",
        status: "complete",
        createdAt: now,
      },
    ],
  };
}

function deriveTitle(prompt: string) {
  const compact = prompt.replace(/\s+/g, " ").trim();
  if (!compact) return "Land-use feasibility";
  return compact.length > 42 ? `${compact.slice(0, 39)}...` : compact;
}

function formatSessionTime(timestamp: number) {
  const diff = Date.now() - timestamp;
  if (diff < 60_000) return "now";
  if (diff < 3_600_000) return `${Math.max(1, Math.round(diff / 60_000))}m`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h`;
  return `${Math.round(diff / 86_400_000)}d`;
}

function latestToolStatus(message: ConsoleMessage | undefined) {
  if (!message?.toolActivity?.length) return null;
  for (let index = message.toolActivity.length - 1; index >= 0; index -= 1) {
    const activity = message.toolActivity[index];
    if (activity.status === "running") {
      return activity.message || `Using ${toolLabel(activity.tool)}`;
    }
  }
  const completed = message.toolActivity[message.toolActivity.length - 1];
  return completed ? `Completed ${toolLabel(completed.tool)}` : null;
}

function readStoredSessions(): AgentSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as AgentSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function Logo() {
  return (
    <Link href="/" className="coded-logo analyze-logo" aria-label="PlotLot home">
      <span className="coded-logo-mark" aria-hidden="true">
        <svg viewBox="0 0 64 64" role="img">
          <rect x="7" y="7" width="50" height="50" rx="10" fill="#2f6e24" />
          <path d="M19 42V20h16c8 0 13 4 13 11s-5 11-13 11H19Zm8-7h8c4 0 6-1 6-4s-2-4-6-4h-8v8Z" fill="#fbfbf8" />
        </svg>
      </span>
      <span className="coded-logo-word">PlotLot</span>
    </Link>
  );
}

export default function AnalyzePage() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? sessions[0],
    [activeSessionId, sessions],
  );

  const messages = activeSession?.messages ?? [];
  const backendSessionId = activeSession?.backendSessionId ?? null;
  const latestMessageContent = messages[messages.length - 1]?.content ?? "";

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const stored = readStoredSessions();
      const nextSessions = stored.length > 0 ? stored : [createInitialSession()];
      const params = new URLSearchParams(window.location.search);
      const requestedSession = params.get("session");
      const active =
        requestedSession && nextSessions.some((session) => session.id === requestedSession)
          ? requestedSession
          : nextSessions[0].id;
      setSessions(nextSessions);
      setActiveSessionId(active);
      setHydrated(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hydrated || sessions.length === 0) return;
    const handle = window.setTimeout(() => {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [hydrated, sessions]);

  useEffect(() => {
    if (!hydrated || !activeSessionId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("session", activeSessionId);
    window.history.replaceState({}, "", url.toString());
  }, [activeSessionId, hydrated]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [latestMessageContent, messages.length, isStreaming]);

  useEffect(() => {
    if (!sidebarOpen) return;
    document.body.classList.add("sidebar-open");
    return () => document.body.classList.remove("sidebar-open");
  }, [sidebarOpen]);

  useEffect(() => {
    if (!isStreaming) {
      inputRef.current?.focus();
    }
  }, [isStreaming, activeSessionId]);

  function updateActiveSession(updater: (session: AgentSession) => AgentSession) {
    setSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId ? updater(session) : session,
      ),
    );
  }

  function selectSession(sessionId: string) {
    if (isStreaming) return;
    setActiveSessionId(sessionId);
    setSidebarOpen(false);
  }

  function createSession() {
    if (isStreaming) return;
    const next = createInitialSession();
    setSessions((current) => [next, ...current]);
    setActiveSessionId(next.id);
    setSidebarOpen(false);
  }

  const handleSubmit = async (event?: FormEvent<HTMLFormElement>, override?: string) => {
    event?.preventDefault();
    if (!activeSession) return;
    const messageText = (override ?? input).trim();
    if (!messageText || isStreaming) return;

    const history: ChatMessageData[] = activeSession.messages
      .filter((message) => message.id !== "welcome")
      .map((message) => ({ role: message.role, content: message.content }));
    const userMessage: ConsoleMessage = {
      id: createId("user"),
      role: "user",
      content: messageText,
    };
    const assistantId = createId("assistant");
    const assistantMessage: ConsoleMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      toolActivity: [],
      thinking: [],
      isStreaming: true,
    };

    const shouldRetitle =
      activeSession.messages.filter((message) => message.id !== "welcome").length === 0;

    setInput("");
    setIsStreaming(true);
    setSessions((current) =>
      current.map((session) =>
        session.id === activeSession.id
          ? {
              ...session,
              title: shouldRetitle ? deriveTitle(messageText) : session.title,
              subtitle: "Active zoning conversation",
              updatedAt: Date.now(),
              messages: [...session.messages, userMessage, assistantMessage],
              tasks: [],
              browserActions: [],
              events: [
                {
                  id: createId("event"),
                  kind: "turn",
                  title: "User turn",
                  detail: messageText,
                  status: "running",
                  createdAt: Date.now(),
                },
                ...session.events.filter((item) => item.status !== "attention"),
              ],
            }
          : session,
      ),
    );

    let streamedContent = "";

    await streamChat(
      messageText,
      history,
      null,
      (token) => {
        streamedContent += token;
        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? { ...message, content: streamedContent, isStreaming: true }
              : message,
          ),
        }));
      },
      (fullContent) => {
        streamedContent = fullContent;
        updateActiveSession((session) => ({
          ...session,
          subtitle: "Latest analysis complete",
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? { ...message, content: fullContent, isStreaming: false }
              : message,
          ),
          events: [
            {
              id: createId("event"),
              kind: "done" as const,
              title: "Response complete",
              detail: "The agent finished the current land-use reasoning turn.",
              status: "complete" as const,
              createdAt: Date.now(),
            },
            ...session.events.map((item) =>
              item.status === "running" ? { ...item, status: "complete" as const } : item,
            ),
          ].slice(0, 30),
        }));
        setIsStreaming(false);
      },
      (error) => {
        updateActiveSession((session) => ({
          ...session,
          subtitle: "Needs attention",
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: `I could not complete that request: ${error}`,
                  isStreaming: false,
                }
              : message,
          ),
          events: [
            {
              id: createId("event"),
              kind: "error" as const,
              title: "Stream error",
              detail: error,
              status: "attention" as const,
              createdAt: Date.now(),
            },
            ...session.events,
          ].slice(0, 30),
        }));
        setIsStreaming(false);
      },
      backendSessionId,
      (nextBackendSessionId) => {
        updateActiveSession((session) => ({
          ...session,
          backendSessionId: nextBackendSessionId,
          updatedAt: Date.now(),
        }));
      },
      (eventData: ToolUseEvent) => {
        const activity: ToolActivity = {
          id: createId("tool"),
          tool: eventData.tool,
          message: eventData.message,
          status: "running",
        };
        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  toolActivity: [...(message.toolActivity ?? []), activity],
                }
              : message,
          ),
          tasks: [
            {
              id: activity.id,
              type: toolMode(eventData.tool),
              title: `Using ${toolLabel(eventData.tool)}`,
              detail: eventData.message || "Calling a PlotLot capability.",
              status: "running" as const,
              createdAt: Date.now(),
            },
            ...(session.tasks ?? []),
          ].slice(0, 30),
          events: [
            {
              id: createId("event"),
              kind: "tool" as const,
              title: `Using ${toolLabel(eventData.tool)}`,
              detail: eventData.message || "Calling a PlotLot capability.",
              status: "running" as const,
              createdAt: Date.now(),
            },
            {
              id: createId("event"),
              kind: "evidence" as const,
              title: "Evidence trail updated",
              detail: "Tool activity will be attached to this analysis turn.",
              status: "queued" as const,
              createdAt: Date.now(),
            },
            ...session.events,
          ].slice(0, 30),
        }));
      },
      (toolResult: ToolResultEvent) => {
        const tool = toolResult.tool;
        const rawStatus = toolResult.status ?? "complete";
        const nextStatus: ToolActivity["status"] =
          rawStatus === "error"
            ? "error"
            : rawStatus === "blocked" || rawStatus === "approval_required"
              ? "blocked"
              : "complete";

        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  toolActivity: (message.toolActivity ?? []).map((activity) =>
                    activity.tool === tool && activity.status === "running"
                      ? { ...activity, status: nextStatus }
                      : activity,
                  ),
                }
              : message,
          ),
          events: session.events.map((item) =>
            item.kind === "tool" && item.title.includes(toolLabel(tool))
              ? { ...item, status: nextStatus === "complete" ? ("complete" as const) : ("attention" as const) }
              : item,
          ),
          tasks: (session.tasks ?? []).map((task) =>
            task.title.includes(toolLabel(tool)) && task.status === "running"
              ? { ...task, status: nextStatus === "complete" ? ("complete" as const) : ("attention" as const) }
              : task,
          ),
        }));
      },
      (thinking: ThinkingEvent) => {
        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? { ...message, thinking: [...(message.thinking ?? []), thinking] }
              : message,
          ),
          events: [
            {
              id: createId("event"),
              kind: "thinking" as const,
              title: thinking.step,
              detail: thinking.thoughts.join(" "),
              status: "running" as const,
              createdAt: Date.now(),
            },
            ...session.events,
          ].slice(0, 30),
        }));
      },
      (taskEvent: AgentTaskEvent) => {
        const taskId = taskEvent.task_id || createId("task");
        updateActiveSession((session) => {
          const currentTasks = session.tasks ?? [];
          const existing = currentTasks.find((task) => task.id === taskId);
          const nextStatus =
            taskEvent.status ||
            (taskEvent.type === "task_complete" ? "complete" : "running");
          const nextTask: AgentTask = {
            id: taskId,
            type: taskEvent.task_type || existing?.type || "agent",
            title: taskTitleFromEvent(taskEvent),
            detail: taskDetailFromEvent(taskEvent),
            status: nextStatus,
            percent: taskEvent.percent ?? existing?.percent,
            durationMs: taskEvent.duration_ms ?? existing?.durationMs,
            url: taskEvent.url ?? existing?.url,
            screenshotB64: taskEvent.screenshot_b64 ?? existing?.screenshotB64,
            citations: taskEvent.citations ?? existing?.citations,
            createdAt: existing?.createdAt ?? Date.now(),
          };
          return {
            ...session,
            updatedAt: Date.now(),
            tasks: existing
              ? currentTasks.map((task) => (task.id === taskId ? nextTask : task))
              : [nextTask, ...currentTasks].slice(0, 30),
          };
        });
      },
      (browserAction: BrowserActionEvent) => {
        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          browserActions: [browserAction, ...(session.browserActions ?? [])].slice(0, 30),
          events: [
            {
              id: createId("event"),
              kind: "tool" as const,
              title: "Browser action",
              detail: browserActionTitle(browserAction),
              status: "running" as const,
              createdAt: Date.now(),
            },
            ...session.events,
          ].slice(0, 30),
        }));
      },
      (reasoningEvent: ReasoningEvent) => {
        const thinking = reasoningToThinking(reasoningEvent);
        updateActiveSession((session) => ({
          ...session,
          updatedAt: Date.now(),
          messages: session.messages.map((message) =>
            message.id === assistantId
              ? { ...message, thinking: [...(message.thinking ?? []), thinking] }
              : message,
          ),
          events: [
            {
              id: createId("event"),
              kind: "thinking" as const,
              title: thinking.step,
              detail: thinking.thoughts.join(" "),
              status: "running" as const,
              createdAt: Date.now(),
            },
            ...session.events,
          ].slice(0, 30),
        }));
      },
    );
  };

  const completedTools = messages
    .flatMap((message) => message.toolActivity ?? [])
    .filter((activity) => activity.status === "complete");
  const visibleTasks = (activeSession?.tasks ?? []).slice(0, 8);
  const latestBrowserAction = (activeSession?.browserActions ?? [])[0];
  const allToolActivity = messages.flatMap((message) => message.toolActivity ?? []);
  const currentTool =
    [...allToolActivity].reverse().find((activity) => activity.status === "running") ??
    allToolActivity[allToolActivity.length - 1];
  const latestUser = [...messages].reverse().find((message) => message.role === "user");
  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const toolStatus = latestToolStatus(latestAssistant);
  const computerEvents = (activeSession?.events ?? [])
    .filter((eventItem) => ["thinking", "tool", "evidence", "done", "error"].includes(eventItem.kind))
    .slice(0, 5);
  const stage = isStreaming
    ? {
        label: "Gathering evidence",
        detail: "PlotLot is streaming tool activity and reasoning through the current turn.",
        tone: "active",
      }
    : latestAssistant && latestAssistant.id !== "welcome"
      ? {
          label: "Follow-up ready",
          detail: "The latest answer is ready for citations, scenario testing, or a memo-quality rewrite.",
          tone: "ready",
        }
      : {
          label: "Ready",
          detail: "Start with a parcel, district, owner, ordinance, or development scenario to open the run.",
          tone: "idle",
        };
  const planProgress = latestAssistant && latestAssistant.id !== "welcome"
    ? [true, completedTools.length > 0 || isStreaming, !isStreaming, !isStreaming]
    : [false, false, false, false];

  return (
    <main className="coded-site analyze-shell">
      <aside
        className={sidebarOpen ? "analyze-sidebar open" : "analyze-sidebar"}
        data-testid="agent-session-sidebar"
        aria-label="Analysis sessions"
      >
        <div className="analyze-sidebar-brand">
          <Logo />
          <button type="button" onClick={createSession} disabled={isStreaming}>
            New
          </button>
        </div>

        <div className="analyze-sidebar-section">
          <p>Workspace</p>
          <strong>PlotLot Feasibility</strong>
          <span>Sites, zoning, evidence, reports</span>
        </div>

        <div className="analyze-session-list" aria-label="Saved analysis sessions">
          {sessions.map((session) => (
            <button
              className={session.id === activeSessionId ? "active" : ""}
              key={session.id}
              onClick={() => selectSession(session.id)}
              type="button"
            >
              <span>{session.title}</span>
              <small>{session.subtitle}</small>
              <em>{formatSessionTime(session.updatedAt)}</em>
            </button>
          ))}
        </div>
      </aside>

      <section className="analyze-workspace">
        <header className="analyze-topbar">
          <button
            className="analyze-sidebar-toggle"
            type="button"
            onClick={() => setSidebarOpen((value) => !value)}
            aria-label="Toggle sessions"
          >
            {sidebarOpen ? "Close" : "Sessions"}
          </button>
          <div>
            <span>PlotLot Agent</span>
            <h1>Land-use intelligence console.</h1>
          </div>
          <nav className="analyze-nav" aria-label="Analyze navigation">
            <Link href="/">Product</Link>
            <Link href="/workspace">Workspace</Link>
            <Link href="/reference">Reference</Link>
          </nav>
          <span className={isStreaming ? "analyze-live active" : "analyze-live"}>
            {isStreaming ? "Reasoning" : "Ready"}
          </span>
        </header>

        <section className="analyze-main">
          <section className="analyze-console" aria-label="PlotLot agent console">
            <div className="analyze-console-top">
              <div>
                <span>{activeSession?.subtitle ?? "New session"}</span>
                <h2>{activeSession?.title ?? "Land-use feasibility"}</h2>
              </div>
              <div className="analyze-model-pill">Agentic zoning analyst</div>
            </div>

            <div className="analyze-messages" aria-live="polite">
              {messages.map((message) => (
                <article className={`analyze-message ${message.role}`} key={message.id}>
                  <div className="analyze-avatar" aria-hidden="true">
                    {message.role === "user" ? "You" : "PL"}
                  </div>
                  <div className="analyze-message-body">
                    <div className="analyze-message-label">
                      {message.role === "user" ? "You" : "PlotLot"}
                    </div>
                    {message.thinking && message.thinking.length > 0 && (
                      <div className="analyze-thinking">
                        {message.thinking.map((thinking, index) => (
                          <div key={`${message.id}-thinking-${index}`}>
                            <strong>{thinking.step}</strong>
                            <span>{thinking.thoughts.join(" ")}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {message.toolActivity && message.toolActivity.length > 0 && (
                      <div className="analyze-tools">
                        {message.toolActivity.map((activity) => (
                          <span
                            className={activity.status === "complete" ? "complete" : ""}
                            key={activity.id}
                          >
                            {activity.status === "complete"
                              ? `Used ${activity.tool}`
                              : activity.message || `Using ${toolLabel(activity.tool)}`}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="analyze-markdown">
                      {message.content || (message.isStreaming ? "Working through it..." : "") ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content || "Working through it..."}
                        </ReactMarkdown>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="analyze-suggestions" aria-label="Suggested prompts">
              {suggestions.map((suggestion) => (
                <button
                  disabled={isStreaming}
                  key={suggestion}
                  onClick={() => void handleSubmit(undefined, suggestion)}
                  type="button"
                >
                  {suggestion}
                </button>
              ))}
            </div>

            <form className="analyze-composer" onSubmit={(event) => void handleSubmit(event)}>
              <div className="analyze-composer-box">
                <textarea
                  aria-label="Ask PlotLot"
                  data-testid="agent-input"
                  disabled={isStreaming}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleSubmit();
                    }
                  }}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Ask about a parcel, zoning district, owner, ordinance, or development scenario..."
                  ref={inputRef}
                  rows={2}
                  value={input}
                />
                <div className="analyze-composer-actions">
                  <span>{backendSessionId ? `Session ${backendSessionId.slice(0, 8)}` : "New backend session"}</span>
                  <button data-testid="send-button" disabled={isStreaming || !input.trim()} type="submit">
                    Send
                  </button>
                </div>
              </div>
            </form>
          </section>

          <aside className="analyze-rail" aria-label="Agent context">
            <section className="analyze-rail-card analyze-computer-card" data-testid="analyze-computer-card">
              <div className="analyze-computer-header">
                <div className="analyze-computer-icon" aria-hidden="true">
                  <span />
                </div>
                <div>
                  <p className="coded-kicker">Browser-use ready</p>
                  <h3>PlotLot Computer</h3>
                </div>
                <span className={isStreaming ? "analyze-computer-state active" : "analyze-computer-state"}>
                  {isStreaming ? "Executing task..." : "Idle"}
                </span>
              </div>

              <div className="analyze-computer-viewport" aria-label="Agent work preview">
                <div className="analyze-browser-chrome" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <strong>
                    {latestBrowserAction?.url ??
                      (toolMode(currentTool?.tool ?? "") === "browser" ? "web source" : "source review")}
                  </strong>
                </div>
                <div className={`analyze-computer-preview ${isStreaming ? "active" : ""}`}>
                  {latestBrowserAction?.screenshot_b64 ? (
                    // eslint-disable-next-line @next/next/no-img-element -- Browser-use screenshots arrive as short-lived base64 frames, not optimized static assets.
                    <img
                      alt="Latest browser-use viewport"
                      className="analyze-browser-screenshot"
                      src={`data:image/jpeg;base64,${latestBrowserAction.screenshot_b64}`}
                    />
                  ) : (
                    <div className="analyze-preview-map" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </div>
                  )}
                  <strong>{computerActionLabel(currentTool)}</strong>
                  <p>
                    {latestBrowserAction?.extracted_text ??
                      latestBrowserAction?.selector ??
                      latestBrowserAction?.value ??
                      currentTool?.message ??
                      "When the agent browses, searches ordinances, or inspects parcel data, that activity appears here."}
                  </p>
                </div>
              </div>

              <div className="analyze-computer-events">
                {computerEvents.length > 0 ? (
                  computerEvents.map((eventItem) => (
                    <div className={eventItem.status} key={eventItem.id}>
                      <span>{eventItem.kind}</span>
                      <strong>{eventItem.title}</strong>
                      <p>{eventItem.detail}</p>
                    </div>
                  ))
                ) : (
                  <div className="queued">
                    <span>ready</span>
                    <strong>Waiting for first action</strong>
                    <p>Ask a zoning or feasibility question to start the visible work loop.</p>
                  </div>
                )}
              </div>
            </section>

            <section className="analyze-rail-card analyze-task-card" data-testid="analyze-task-timeline-card">
              <p className="coded-kicker">Visible work</p>
              <h3>Task timeline</h3>
              <div className="analyze-agent-tasks">
                {visibleTasks.length > 0 ? (
                  visibleTasks.map((task) => (
                    <div className={task.status} key={task.id}>
                      <span>{task.type}</span>
                      <strong>{task.title}</strong>
                      <p>{task.detail}</p>
                      <small>
                        {task.status}
                        {typeof task.percent === "number" ? ` · ${task.percent}%` : ""}
                        {typeof task.durationMs === "number" ? ` · ${task.durationMs}ms` : ""}
                      </small>
                    </div>
                  ))
                ) : (
                  <div className="queued">
                    <span>queued</span>
                    <strong>Waiting for structured tasks</strong>
                    <p>Tool calls, browser actions, and evidence steps will appear here as rows.</p>
                    <small>ready</small>
                  </div>
                )}
              </div>
            </section>

            <section className="analyze-rail-card" data-testid="analyze-status-card">
              <p className="coded-kicker">Status</p>
              <h3>Run state</h3>
              <span className={`analyze-stage-pill ${stage.tone}`}>{stage.label}</span>
              <p>{stage.detail}</p>
              <div className="analyze-evidence-list">
                <div>
                  <strong>Session</strong>
                  <span>{backendSessionId ? backendSessionId.slice(0, 8) : "New backend session"}</span>
                </div>
                <div>
                  <strong>Prompt</strong>
                  <span>{latestUser?.content ?? "No question yet"}</span>
                </div>
                <div>
                  <strong>Live tool</strong>
                  <span>{toolStatus ?? "Waiting for the first tool call"}</span>
                </div>
              </div>
            </section>

            <section className="analyze-rail-card" data-testid="analyze-plan-card">
              <p className="coded-kicker">Plan</p>
              <h3>Consultant loop</h3>
              <div className="analyze-plan-list">
                {analyzePlan.map((step, index) => (
                  <div key={step.label}>
                    <span className={planProgress[index] ? "complete" : ""}>
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <strong>{step.label}</strong>
                      <p>{step.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="analyze-rail-card" data-testid="analyze-evidence-card">
              <p className="coded-kicker">Evidence</p>
              <h3>{completedTools.length > 0 ? "Sources touched" : "Awaiting sources"}</h3>
              <div className="analyze-evidence-list">
                {completedTools.length > 0 ? (
                  completedTools.slice(-4).map((activity) => (
                    <div key={activity.id}>
                      <strong>{toolLabel(activity.tool)}</strong>
                      <span>{activity.message || "Tool result captured for this turn."}</span>
                    </div>
                  ))
                ) : (
                  <div>
                    <strong>Source ledger</strong>
                    <span>Ordinance, parcel, and ownership evidence appears as tools run.</span>
                  </div>
                )}
              </div>
            </section>

            <section className="analyze-rail-card" data-testid="analyze-actions-card">
              <p className="coded-kicker">Next actions</p>
              <h3>What to pressure-test next</h3>
              <div className="analyze-risk-grid">
                {riskSignals.map((risk) => (
                  <span key={risk}>{risk}</span>
                ))}
              </div>
              <div className="analyze-next-actions">
                {suggestions.map((suggestion) => (
                  <button
                    key={`rail-${suggestion}`}
                    type="button"
                    disabled={isStreaming}
                    onClick={() => void handleSubmit(undefined, suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
              {latestAssistant?.content ? (
                <p className="analyze-rail-note">
                  Latest answer captured. Use the next turn to ask for citations, calculations, or a memo.
                </p>
              ) : (
                <p className="analyze-rail-note">
                  The first response will turn this rail into a running evidence and review surface.
                </p>
              )}
            </section>
          </aside>
        </section>
      </section>
    </main>
  );
}
