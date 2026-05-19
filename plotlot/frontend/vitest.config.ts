import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/ui/setup.ts"],
    include: ["./tests/ui/**/*.test.ts?(x)", "./tests/unit/**/*.test.ts?(x)"],
    css: true,
  },
});
