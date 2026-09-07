import { type Page, type APIRequestContext } from "@playwright/test";
import { expect, test } from "./fixtures";

export { test, expect };

export interface BackendPreflight {
  status: string;
  healthy: boolean;
  reachable: boolean;
  reason: string;
  body: Record<string, unknown>;
}

const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const HEALTH_URL = new URL("/health", BACKEND_BASE_URL).toString();

async function parseHealthResponse(
  health: Response | { ok(): boolean; status(): number; json(): Promise<unknown> },
): Promise<BackendPreflight> {
  const ok = typeof health.ok === "function" ? health.ok() : health.ok;
  const statusCode = typeof health.status === "function" ? health.status() : health.status;

  if (!ok) {
    return {
      status: `http-${statusCode}`,
      healthy: false,
      reachable: false,
      reason: `Backend preflight failed with HTTP ${statusCode} at ${HEALTH_URL}`,
      body: {},
    };
  }

  const body = (await health.json()) as Record<string, unknown>;
  const status = typeof body.status === "string" ? body.status : "unknown";
  const checks =
    typeof body.checks === "object" && body.checks !== null
      ? (body.checks as Record<string, unknown>)
      : {};
  const database = checks.database;
  const databaseHealthy =
    database === "ok" ||
    (typeof database === "object" &&
      database !== null &&
      (database as Record<string, unknown>).status === "ok");
  const healthy = status === "healthy" && databaseHealthy;
  return {
    status,
    healthy,
    reachable: true,
    reason:
      healthy
        ? "Backend and database healthy"
        : `Backend preflight expected status=healthy and checks.database=ok but got status=${status}, database=${JSON.stringify(database)}`,
    body,
  };
}

export async function getBackendPreflight(
  request?: APIRequestContext,
): Promise<BackendPreflight> {
  if (process.env.PLOTLOT_QUALITY_MUTATION === "unhealthy-db") {
    return {
      status: "unhealthy",
      healthy: false,
      reachable: true,
      reason:
        "Backend preflight expected status=healthy and checks.database=ok but got status=unhealthy, database=\"error\"",
      body: { status: "unhealthy", checks: { database: "error" } },
    };
  }

  try {
    if (request) {
      const health = await request.get(HEALTH_URL, { timeout: 5_000 });
      return parseHealthResponse(health);
    }

    const health = await fetch(HEALTH_URL);
    return parseHealthResponse(health);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      status: "unreachable",
      healthy: false,
      reachable: false,
      reason: `Backend preflight could not reach ${HEALTH_URL}: ${message}`,
      body: {},
    };
  }
}

export async function requireHealthyBackend(
  request?: APIRequestContext,
): Promise<BackendPreflight> {
  const preflight = await getBackendPreflight(request);
  if (preflight.healthy) return preflight;

  if (process.env.CI || process.env.PLOTLOT_RELEASE_GATE === "1") {
    throw new Error(
      `${preflight.reason}. Release db-backed lane must fail instead of silently downgrading.`,
    );
  }

  return {
    ...preflight,
    reason: `${preflight.reason}. Local db-backed lane is skipping by contract.`,
  };
}

export async function gotoHome(page: Page) {
  await page.goto("/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("send-button")).toBeVisible();
  await expect(page.getByTestId("lookup-input")).toBeVisible();
  await page.waitForTimeout(300);
}

export async function gotoLanding(page: Page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("public-homepage")).toBeVisible();
}

export async function switchToAgent(page: Page) {
  const agentInput = page.getByTestId("agent-input");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.getByRole("button", { name: "Agent" }).click();
    if (await agentInput.isVisible().catch(() => false)) break;
    await page.waitForTimeout(200);
  }
  await expect(agentInput).toBeVisible();
  await expect(page.getByTestId("send-button")).toBeVisible();
  await expect(page).toHaveURL(/\/workspace(?:\?mode=(?:agent|lookup))?$/);
}

export async function switchToLookup(page: Page) {
  const lookupInput = page.getByTestId("lookup-input");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.getByRole("button", { name: "Lookup" }).click();
    if (await lookupInput.isVisible().catch(() => false)) break;
    await page.waitForTimeout(200);
  }
  await expect(page).toHaveURL(/\/workspace\?mode=lookup$/);
  await expect(lookupInput).toBeVisible();
  await expect(page.getByTestId("send-button")).toBeVisible();
}

export async function runLookupFlow(
  page: Page,
  address: string,
) {
  const input = page.getByTestId("lookup-input");
  const sendButton = page.getByTestId("send-button");

  await page.route("**/api/v1/autocomplete**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ suggestions: [] }),
    }));

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await input.fill("");
    await input.fill(address);
    await page.waitForTimeout(150);
    if (
      (await input.inputValue().catch(() => "")) === address &&
      (await sendButton.isEnabled().catch(() => false))
    ) {
      break;
    }
  }

  await expect(input).toHaveValue(address, { timeout: 10_000 });
  await expect(sendButton).toBeEnabled({ timeout: 10_000 });
  await sendButton.click();
}

export async function waitForReport(page: Page) {
  await expect(page.getByTestId("report-root")).toBeVisible({ timeout: 90_000 });
}

interface StubAnalyzeOptions {
  statuses?: Array<Record<string, unknown>>;
  result?: Record<string, unknown>;
  error?: { detail: string; error_type?: string };
}

export async function stubAnalyzeStream(
  page: Page,
  options: StubAnalyzeOptions,
) {
  const body = [
    ...(options.statuses ?? []).map(
      (status) => `event: status\ndata: ${JSON.stringify(status)}\n\n`,
    ),
    ...(options.result
      ? [`event: result\ndata: ${JSON.stringify(options.result)}\n\n`]
      : []),
    ...(options.error
      ? [`event: error\ndata: ${JSON.stringify(options.error)}\n\n`]
      : []),
  ].join("");

  await page.route("**/api/v1/analyze/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
}

interface StubAgentChatOptions {
  fullContent: string;
  sessionId?: string;
  toolMessage?: string;
  toolName?: string;
}

export async function stubAgentChatErrorSse(
  page: Page,
  detail: string,
  sessionId = "test-session",
) {
  const body = [
    `event: session\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
    `event: error\ndata: ${JSON.stringify({ detail })}\n\n`,
  ].join("");

  await page.route("**/api/v1/chat", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
}

export async function stubAgentChatSse(
  page: Page,
  {
    fullContent,
    sessionId = "test-session",
    toolMessage = "Using report context",
    toolName = "report_context",
  }: StubAgentChatOptions,
) {
  const tokens = fullContent.split(/(\s+)/).filter(Boolean);
  const body = [
    `event: session\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
    `event: tool_use\ndata: ${JSON.stringify({ tool: toolName, args: {}, message: toolMessage })}\n\n`,
    ...tokens.map(
      (token) => `event: token\ndata: ${JSON.stringify({ content: token })}\n\n`,
    ),
    `event: tool_result\ndata: ${JSON.stringify({ tool: toolName })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ full_content: fullContent })}\n\n`,
  ].join("");

  await page.route("**/api/v1/chat", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
}
