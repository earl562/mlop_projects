"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { APIProvider, useMapsLibrary } from "@vis.gl/react-google-maps";

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

interface AddressAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (address: string) => void;
  placeholder?: string;
  disabled?: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

function AutocompleteInner({
  value,
  onChange,
  onSelect,
  placeholder,
  disabled,
  inputRef,
}: AddressAutocompleteProps) {
  const places = useMapsLibrary("places");
  const [predictions, setPredictions] = useState<google.maps.places.AutocompletePrediction[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const serviceRef = useRef<google.maps.places.AutocompleteService | null>(null);
  const sessionTokenRef = useRef<google.maps.places.AutocompleteSessionToken | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!places) return;
    serviceRef.current = new places.AutocompleteService();
    sessionTokenRef.current = new places.AutocompleteSessionToken();
  }, [places]);

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

  const fetchPredictions = useCallback(
    (input: string) => {
      if (!serviceRef.current || !sessionTokenRef.current || input.length < 3) {
        setPredictions([]);
        setShowDropdown(false);
        return;
      }

      serviceRef.current.getPlacePredictions(
        {
          input,
          sessionToken: sessionTokenRef.current,
          componentRestrictions: { country: "us" },
          types: ["address"],
        },
        (results, status) => {
          if (status === google.maps.places.PlacesServiceStatus.OK && results) {
            // Filter to Florida addresses
            const flPredictions = results.filter(
              (p) =>
                p.description.includes(", FL") ||
                p.description.includes("Florida"),
            );
            setPredictions(flPredictions.length > 0 ? flPredictions : results.slice(0, 5));
            setShowDropdown(flPredictions.length > 0 || results.length > 0);
            setSelectedIndex(-1);
          } else {
            setPredictions([]);
            setShowDropdown(false);
          }
        },
      );
    },
    [],
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    onChange(val);
    fetchPredictions(val);
  };

  const handleSelectPrediction = (prediction: google.maps.places.AutocompletePrediction) => {
    const address = prediction.description;
    onChange(address);
    setPredictions([]);
    setShowDropdown(false);
    // Reset session token after selection
    if (places) {
      sessionTokenRef.current = new places.AutocompleteSessionToken();
    }
    onSelect(address);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown || predictions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < predictions.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : predictions.length - 1));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      handleSelectPrediction(predictions[selectedIndex]);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  return (
    <div ref={wrapperRef} className="relative flex-1">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onFocus={() => predictions.length > 0 && setShowDropdown(true)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full bg-transparent text-sm text-[var(--text-primary)] placeholder-stone-400 outline-none"
        autoComplete="off"
      />
      {showDropdown && predictions.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-lg">
          {predictions.map((prediction, index) => (
            <button
              key={prediction.place_id}
              onClick={() => handleSelectPrediction(prediction)}
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
                <div className="truncate font-medium">
                  {prediction.structured_formatting.main_text}
                </div>
                <div className="truncate text-xs text-stone-500">
                  {prediction.structured_formatting.secondary_text}
                </div>
              </div>
            </button>
          ))}
          <div className="border-t border-[var(--border)] px-3 py-1.5">
            <span className="text-xs text-stone-500">Powered by Google</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AddressAutocomplete(props: AddressAutocompleteProps) {
  // Without API key, render a plain input
  if (!MAPS_KEY) {
    return (
      <input
        ref={props.inputRef}
        type="text"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        disabled={props.disabled}
        className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder-stone-400 outline-none"
      />
    );
  }

  return (
    <APIProvider apiKey={MAPS_KEY}>
      <AutocompleteInner {...props} />
    </APIProvider>
  );
}
