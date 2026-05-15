import { defineConfig, devices } from "@playwright/test";

// The Codex sandbox disallows binding to 0.0.0.0, so keep the dev server on loopback.
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 120_000,
  globalSetup: require.resolve("./tests/global-setup"),
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  outputDir: "./test-results",
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      url: BASE_URL,
      reuseExistingServer: true,
      timeout: 90_000,
      env: { PLAYWRIGHT_TESTING: "1" },
    },
  ],
});
