"use client";

import { FormEvent, RefObject } from "react";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import ModeToggle from "@/components/ModeToggle";
import type { AppMode } from "@/components/ModeToggle";

interface InputBarProps {
  inputRef: RefObject<HTMLInputElement | null>;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: FormEvent) => void;
  onAddressSelect: (address: string) => void;
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  placeholder?: string;
  disabled?: boolean;
  isProcessing?: boolean;
}

export default function InputBar({
  inputRef,
  value,
  onChange,
  onSubmit,
  onAddressSelect,
  mode,
  onModeChange,
  placeholder = "Enter an address or ask a question...",
  disabled = false,
  isProcessing = false,
}: InputBarProps) {
  return (
    <div className="mx-auto max-w-[1024px]">
      <form onSubmit={onSubmit}>
        <div
          className="flex items-center gap-1.5 rounded-[30px] border border-[var(--border)] bg-[var(--bg-surface)] px-2.5 py-2.5 shadow-[var(--shadow-card)] transition-all focus-within:border-[var(--brand)] focus-within:ring-2 focus-within:ring-[var(--brand-subtle)] sm:gap-2 sm:px-4 sm:py-3"
        >
          {mode === "lookup" ? (
            <AddressAutocomplete
              inputRef={inputRef}
              value={value}
              onChange={onChange}
              onSelect={onAddressSelect}
              placeholder={placeholder}
              disabled={disabled}
            />
          ) : (
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              disabled={disabled}
              className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none sm:text-base"
              data-testid="agent-input"
            />
          )}
          <ModeToggle mode={mode} onChange={onModeChange} />
          <button
            type="submit"
            disabled={!value.trim() || isProcessing}
            aria-label="Send message"
            data-testid="send-button"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--bg-primary)] transition-all hover:opacity-90 disabled:opacity-30 sm:h-11 sm:w-11"
          >
            {isProcessing ? (
              <svg className="h-3.5 w-3.5 animate-spin sm:h-4 sm:w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-3.5 w-3.5 sm:h-4 sm:w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
