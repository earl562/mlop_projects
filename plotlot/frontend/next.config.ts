import path from "node:path";

import type { NextConfig } from "next";

// Keep tracing and Turbopack aligned at the repo root for monorepo/Vercel builds.
const workspaceRoot = path.join(__dirname, "..", "..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: workspaceRoot,
  devIndicators: process.env.PLAYWRIGHT_TESTING === "1" ? false : undefined,
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
