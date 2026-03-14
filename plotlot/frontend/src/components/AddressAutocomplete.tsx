"use client";

import { useState, useRef, useCallback, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AddressAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (address: string) => void;
  placeholder?: string;
  disabled?: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

interface Suggestion {
  address: string;
  street: string;
  city: string;
  state: string;
  zip: string;
}

export default function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder,
  disabled,
  inputRef,
}: AddressAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isSearching, setIsSearching] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const fetchSuggestions = useCallback(async (query: string) => {
    if (query.length < 3) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }

    setIsSearching(true);
    try {
      const resp = await fetch(`${API_URL}/api/v1/autocomplete?q=${encodeURIComponent(query)}`);
      if (!resp.ok) throw new Error("API error");
      const data = await resp.json();
      const results: Suggestion[] = data.suggestions || [];
      setSuggestions(results);
      setShowDropdown(results.length > 0);
      setSelectedIndex(-1);
    } catch {
      setSuggestions([]);
      setShowDropdown(false);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    onChange(val);

    // Debounce API calls (300ms)
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(val), 300);
  };

  const handleSelect = (suggestion: Suggestion) => {
    onChange(suggestion.address);
    setSuggestions([]);
    setShowDropdown(false);
    onSelect(suggestion.address);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown || suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[selectedIndex]);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  return (
    <div ref={wrapperRef} className="relative z-50 flex-1">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full bg-transparent text-sm text-[var(--text-primary)] placeholder-stone-400 outline-none"
        autoComplete="off"
        aria-label={placeholder || "Enter an address"}
      />
      {/* Loading indicator */}
      {isSearching && !showDropdown && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-lg">
          <div className="flex items-center gap-2 px-3 py-3 text-xs text-stone-500">
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Searching addresses...
          </div>
        </div>
      )}
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-lg">
          {suggestions.map((s, index) => (
            <button
              key={s.address}
              onClick={() => handleSelect(s)}
              className={`flex w-full items-center gap-3 px-3 py-3 text-left text-sm transition-colors ${
                index === selectedIndex
                  ? "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface-raised)]"
              }`}
            >
              <svg
                className="h-4 w-4 shrink-0 text-stone-500"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{s.street}</div>
                <div className="truncate text-xs text-stone-500">
                  {s.city}{s.state ? `, ${s.state}` : ""}{s.zip ? ` ${s.zip}` : ""}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
