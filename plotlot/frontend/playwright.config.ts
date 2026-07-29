import { defineConfig, devices } from "@playwright/test";

// The Codex sandbox disallows binding to 0.0.0.0, so keep the dev server on loopback.
const PLAYWRIGHT_PORT = process.env.PLAYWRIGHT_PORT ?? "3003";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${PLAYWRIGHT_PORT}`;
const USE_EXTERNAL_WEBSERVER = process.env.PLAYWRIGHT_DISABLE_WEBSERVER === "1";
const REUSE_EXISTING_WEBSERVER = process.env.PLAYWRIGHT_REUSE_SERVER === "1";
const WEB_SERVER_PORT = new URL(BASE_URL).port || PLAYWRIGHT_PORT;
const MATRIX_LANE = process.env.PLOTLOT_MATRIX_LANE ?? "adhoc";
const MATRIX_OUTPUT = `.quality-matrix/playwright-${MATRIX_LANE}.json`;
const DESKTOP_CHROME = { ...devices["Desktop Chrome"] };
const TASK8_ROLE_MATRIX = process.argv.some((argument) => argument.includes("tenant-role-matrix.spec.ts"));
const TASK8_WEBSERVER = {
  command: "node tests/task8-local-auth-webserver.mjs",
  env: {
    NEXT_TELEMETRY_DISABLED: "1",
  },
  reuseExistingServer: false,
  timeout: 180_000,
  url: `${BASE_URL}/api/local-auth/session`,
};

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI || process.env.PLOTLOT_RELEASE_GATE === "1"),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["html", { open: "never" }],
    ["list"],
    ["json", { outputFile: MATRIX_OUTPUT }],
  ],
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  globalSetup: require.resolve("./tests/global-setup"),
  use: {
    baseURL: BASE_URL,
    actionTimeout: 10_000,
    navigationTimeout: 45_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  outputDir: "./test-results",
  projects: [
    {
      name: "chromium",
      testMatch: TASK8_ROLE_MATRIX
        ? ["**/lookup-uat.spec.ts", "**/tenant-role-matrix.spec.ts"]
        : "**/lookup-uat.spec.ts",
      use: DESKTOP_CHROME,
    },
    {
      name: "no-db",
      testMatch: [
        "**/smoke.no-db.spec.ts",
        "**/mutation.spec.ts",
        "**/sidebar-navigation.spec.ts",
        "**/vc-readiness.no-db.spec.ts",
        "**/workspace-routes.no-db.spec.ts",
        "**/lookup-uat.spec.ts",
      ],
      use: DESKTOP_CHROME,
    },
    {
      name: "db-backed",
      testMatch: "**/*.db.spec.ts",
      timeout: 120_000,
      use: DESKTOP_CHROME,
    },
    {
      name: "recorded-real",
      testMatch: "**/recorded-real.spec.ts",
      use: DESKTOP_CHROME,
    },
    {
      name: "live",
      testMatch: ["**/*.live.e2e.spec.ts", "**/*-live.e2e.spec.ts"],
      timeout: 120_000,
      use: DESKTOP_CHROME,
    },
    {
      name: "visual",
      testMatch: "**/design-system.spec.ts",
      timeout: 45_000,
      use: {
        ...DESKTOP_CHROME,
        screenshot: "on",
      },
    },
    {
      name: "accessibility",
      testMatch: "**/accessibility.spec.ts",
      use: DESKTOP_CHROME,
    },
    {
      name: "performance",
      testMatch: "**/performance.spec.ts",
      use: DESKTOP_CHROME,
    },
  ],
  webServer: USE_EXTERNAL_WEBSERVER
    ? undefined
    : TASK8_ROLE_MATRIX
    ? TASK8_WEBSERVER
    : [
        {
          command: `npm run build && npm run start -- --hostname 127.0.0.1 --port ${WEB_SERVER_PORT}`,
          url: BASE_URL,
          reuseExistingServer: REUSE_EXISTING_WEBSERVER,
          timeout: 180_000,
          env: {
            NEXT_TELEMETRY_DISABLED: "1",
            PLAYWRIGHT_TESTING: "1",
          },
        },
      ],
});
