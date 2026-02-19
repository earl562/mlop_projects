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
    <div className="flex h-[500px] flex-col rounded-xl border border-stone-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-stone-200 px-4 py-3">
        <div className="h-2 w-2 rounded-full bg-amber-500" />
        <span className="text-sm font-semibold text-stone-700">PlotLot Agent</span>
        <span className="text-xs text-stone-500">
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
                  ? "bg-amber-50 text-stone-800"
                  : "bg-stone-50 text-stone-700"
              }`}
            >
              {msg.content || (
                <span className="inline-flex items-center gap-1 text-stone-400">
                  <span className="animate-pulse">Thinking</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
                </span>
              )}
              {msg.isStreaming && msg.content && (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-amber-600" />
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
              className="rounded-lg bg-[#f5f0eb] px-2.5 py-1 text-xs text-stone-500 transition-colors hover:bg-[#ede8e0] hover:text-stone-700 disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-stone-200 p-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this property's zoning..."
            disabled={isStreaming}
            className="flex-1 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-800 placeholder-stone-400 outline-none ring-amber-500/20 focus:border-amber-500 focus:ring-2"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
