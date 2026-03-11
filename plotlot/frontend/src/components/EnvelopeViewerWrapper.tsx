"use client";

import dynamic from "next/dynamic";
import type { EnvelopeViewerProps } from "./EnvelopeViewer";

const EnvelopeViewer = dynamic(() => import("./EnvelopeViewer"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[400px] items-center justify-center rounded-lg border border-stone-200 bg-stone-50">
      <div className="flex flex-col items-center gap-2">
        <svg
          className="h-6 w-6 animate-spin text-stone-500"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span className="text-sm text-stone-500">Loading 3D viewer...</span>
      </div>
    </div>
  ),
});

export default function EnvelopeViewerWrapper(props: EnvelopeViewerProps) {
  return <EnvelopeViewer {...props} />;
}
