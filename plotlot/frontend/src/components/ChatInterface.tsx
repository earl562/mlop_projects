"use client";

import { useState, useRef, useEffect, FormEvent, useCallback } from "react";
import { ChatMessageData, ZoningReportData, streamChat } from "@/lib/api";

interface ChatInterfaceProps {
  report: ZoningReportData;
}

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

const SUGGESTIONS = [
  "What can I build on this lot?",
  "Explain the density calculation",
  "What setback variances could I request?",
  "Is this property suitable for multifamily development?",
  "What are the parking requirements?",
];

export default function ChatInterface({ report }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      role: "assistant",
      content: `I've analyzed **${report.formatted_address}** in ${report.municipality}. This is a **${report.zoning_district}** (${report.zoning_description}) zone${report.density_analysis ? ` with a max of **${report.density_analysis.max_units} unit(s)**` : ""}. What would you like to know?`,
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      const userMsg: DisplayMessage = { role: "user", content: text.trim() };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setIsStreaming(true);

      // Build history for API (exclude the initial greeting)
      const history: ChatMessageData[] = messages
        .slice(1)
        .map((m) => ({ role: m.role, content: m.content }));
      history.push({ role: "user", content: text.trim() });

      // Add streaming placeholder
      const placeholderIndex = messages.length + 1;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", isStreaming: true },
      ]);

      try {
        await streamChat(
          text.trim(),
          history.slice(0, -1), // history without current message
          report,
          (token) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant" && last.isStreaming) {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + token,
                };
              }
              return updated;
            });
          },
          () => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, isStreaming: false };
              }
              return updated;
            });
            setIsStreaming(false);
          },
          (error) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant" && last.isStreaming) {
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: `Sorry, I encountered an error: ${error}`,
                  isStreaming: false,
                };
              }
              return updated;
            });
            setIsStreaming(false);
          },
        );
      } catch {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant" && last.isStreaming) {
            updated[updated.length - 1] = {
              role: "assistant",
              content: "Connection failed. Is the backend running?",
              isStreaming: false,
            };
          }
          return updated;
        });
        setIsStreaming(false);
      }
    },
    [messages, isStreaming, report],
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  return (
    <div className="flex h-[500px] flex-col rounded-xl border border-zinc-800 bg-zinc-900/50">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
        <div className="h-2 w-2 rounded-full bg-emerald-400" />
        <span className="text-sm font-semibold text-zinc-300">PlotLot Agent</span>
        <span className="text-xs text-zinc-600">
          {report.zoning_district} | {report.municipality}
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-emerald-600 text-white"
                  : "bg-zinc-800 text-zinc-200"
              }`}
            >
              {msg.content || (
                <span className="inline-flex items-center gap-1 text-zinc-500">
                  <span className="animate-pulse">Thinking</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
                </span>
              )}
              {msg.isStreaming && msg.content && (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-emerald-400" />
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              disabled={isStreaming}
              className="rounded-lg bg-zinc-800/50 px-2.5 py-1 text-xs text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-zinc-800 p-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this property's zoning..."
            disabled={isStreaming}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-sm text-white placeholder-zinc-500 outline-none focus:border-emerald-500"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
