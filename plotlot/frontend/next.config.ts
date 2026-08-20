import path from "node:path";

import type { NextConfig } from "next";

// Keep tracing and Turbopack aligned at the repo root for monorepo/Vercel builds.
const workspaceRoot = path.join(__dirname, "..", "..");
const isPlaywrightTest = process.env.PLAYWRIGHT_TESTING === "1";

const nextConfig: NextConfig = {
  distDir: isPlaywrightTest ? ".next-playwright" : ".next",
  ...(isPlaywrightTest ? {} : { output: "standalone" as const }),
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    root: workspaceRoot,
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.fal.ai",
      },
      {
        protocol: "https",
        hostname: "fal.ai",
      },
    ],
  },
};

export default nextConfig;
