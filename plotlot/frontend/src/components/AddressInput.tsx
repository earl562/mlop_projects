"use client";

import { useState, FormEvent } from "react";

interface AddressInputProps {
  onSubmit: (address: string) => void;
  isLoading: boolean;
}

export default function AddressInput({ onSubmit, isLoading }: AddressInputProps) {
  const [address, setAddress] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (address.trim() && !isLoading) {
      onSubmit(address.trim());
    }
  };

  const examples = [
    "171 NE 209th Ter, Miami, FL 33179",
    "2600 SW 3rd Ave, Miami, FL 33129",
    "1600 S Andrews Ave, Fort Lauderdale, FL 33316",
  ];

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Enter a South Florida property address..."
          className="w-full rounded-xl border border-zinc-700 bg-zinc-800/50 px-5 py-4 pr-28 text-lg text-white placeholder-zinc-500 outline-none ring-emerald-500/40 transition-all focus:border-emerald-500 focus:ring-2"
          disabled={isLoading}
        />
        <button
          type="submit"
          disabled={!address.trim() || isLoading}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Analyzing
            </span>
          ) : (
            "Analyze"
          )}
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <span className="text-xs text-zinc-500">Try:</span>
        {examples.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => { setAddress(ex); onSubmit(ex); }}
            disabled={isLoading}
            className="rounded-md bg-zinc-800/50 px-2.5 py-1 text-xs text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-zinc-600">
        Covers 104 municipalities across Miami-Dade, Broward, and Palm Beach counties
      </p>
    </form>
  );
}
