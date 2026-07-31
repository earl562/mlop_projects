import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT ?? "3003";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;
const useExternalServer = process.env.PLAYWRIGHT_DISABLE_WEBSERVER === "1";

export default defineConfig({
  testDir: ".",
  testMatch: "tenant-role-matrix.spec.ts",
  forbidOnly: true,
  fullyParallel: false,
  reporter: [["list"]],
  retries: 0,
  timeout: 60_000,
  workers: 1,
  projects: [{ name: "chromium", use: devices["Desktop Chrome"] }],
  use: {
    ...devices["Desktop Chrome"],
    actionTimeout: 10_000,
    baseURL,
    navigationTimeout: 45_000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  webServer: useExternalServer
    ? undefined
    : {
        command: `npm run build && npm run start -- --hostname 127.0.0.1 --port ${port}`,
        env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
        reuseExistingServer: false,
        timeout: 300_000,
        url: baseURL,
      },
});
