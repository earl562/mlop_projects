import {
  defineConfig,
  devices,
  type ReporterDescription,
} from "@playwright/test";

// The Codex sandbox disallows binding to 0.0.0.0, so keep the dev server on loopback.
const PLAYWRIGHT_PORT = process.env.PLAYWRIGHT_PORT ?? "3003";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${PLAYWRIGHT_PORT}`;
const USE_EXTERNAL_WEBSERVER = process.env.PLAYWRIGHT_DISABLE_WEBSERVER === "1";
const REUSE_EXISTING_WEBSERVER = process.env.PLAYWRIGHT_REUSE_SERVER === "1";
const WEB_SERVER_PORT = new URL(BASE_URL).port || PLAYWRIGHT_PORT;
const OUTPUT_DIR = process.env.PLOTLOT_PLAYWRIGHT_OUTPUT_DIR ?? "./test-results";
const REPORT_DIR = process.env.PLOTLOT_PLAYWRIGHT_REPORT_DIR ?? "./playwright-report";
const ITERATION_JSON = process.env.PLOTLOT_PLAYWRIGHT_JSON;
const reporters: ReporterDescription[] = [
  ["html", { open: "never", outputFolder: REPORT_DIR }],
  ["list"],
  ...(ITERATION_JSON ? [["json", { outputFile: ITERATION_JSON }]] : []),
] as ReporterDescription[];

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: reporters,
  timeout: 120_000,
  globalSetup: require.resolve("./tests/global-setup"),
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  outputDir: OUTPUT_DIR,
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: USE_EXTERNAL_WEBSERVER
    ? undefined
    : [
        {
          command: `npm run dev -- --hostname 127.0.0.1 --port ${WEB_SERVER_PORT}`,
          url: BASE_URL,
          reuseExistingServer: REUSE_EXISTING_WEBSERVER,
          timeout: 90_000,
          env: { PLAYWRIGHT_TESTING: "1" },
        },
      ],
});
