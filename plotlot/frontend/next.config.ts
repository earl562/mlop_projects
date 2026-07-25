import path from "node:path";

import type { NextConfig } from "next";

// Keep tracing and Turbopack aligned at the repo root for monorepo/Vercel builds.
const workspaceRoot = path.join(__dirname, "..", "..");

const nextConfig: NextConfig = {
  distDir: process.env.PLAYWRIGHT_TESTING === "1" ? ".next-playwright" : ".next",
  output: "standalone",
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
