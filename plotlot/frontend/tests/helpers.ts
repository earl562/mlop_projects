import { expect, Page, APIRequestContext } from "@playwright/test";

export { test } from "@playwright/test";
export { expect };

export interface BackendPreflight {
  status: string;
  healthy: boolean;
  reachable: boolean;
  reason: string;
  body: Record<string, unknown>;
}

const HEALTH_URL = "http://127.0.0.1:8000/health";

async function parseHealthResponse(
  health: Response | { ok(): boolean; status(): number; json(): Promise<unknown> },
): Promise<BackendPreflight> {
  const ok = "ok" in health ? health.ok : health.ok();
  const statusCode = "status" in health ? health.status : health.status();

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
  return {
    status,
    healthy: status === "healthy",
    reachable: true,
    reason:
      status === "healthy"
        ? "Backend healthy"
        : `Backend preflight expected healthy but got ${status}`,
    body,
  };
}

export async function getBackendPreflight(
  request?: APIRequestContext,
): Promise<BackendPreflight> {
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

  if (process.env.CI) {
    throw new Error(
      `${preflight.reason}. CI db-backed lane must fail instead of silently downgrading.`,
    );
  }

  return {
    ...preflight,
    reason: `${preflight.reason}. Local db-backed lane is skipping by contract.`,
  };
}

export async function gotoHome(page: Page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("send-button")).toBeVisible();
  await expect(page.getByTestId("lookup-input")).toBeVisible();
  await page.waitForTimeout(300);
}

export async function switchToAgent(page: Page) {
  await page.getByRole("button", { name: "Agent" }).click();
  await expect(page.getByTestId("send-button")).toBeVisible();
}

export async function switchToLookup(page: Page) {
  await page.getByRole("button", { name: "Lookup" }).click();
  await expect(page.getByTestId("send-button")).toBeVisible();
}

export async function runLookupFlow(
  page: Page,
  address: string,
  dealType: "land" | "wholesale" | "creative-finance" | "hybrid" = "land",
) {
  const input = page.getByTestId("lookup-input");
  const sendButton = page.getByTestId("send-button");

  // In some environments the page can hydrate after the first fill, wiping the input value.
  // Retry until the controlled value "sticks" before attempting to submit.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await input.fill(address);
    if ((await input.inputValue().catch(() => "")) === address) break;
    await page.waitForTimeout(150);
  }

  await expect(input).toHaveValue(address, { timeout: 10_000 });
  await expect(sendButton).toBeEnabled({ timeout: 10_000 });
  await sendButton.click();

  await expect(page.getByTestId("deal-type-selector")).toBeVisible({
    timeout: 10_000,
  });
  await page.getByTestId(`deal-type-${dealType}`).click();

  await expect(page.getByTestId("pipeline-approval-card")).toBeVisible({
    timeout: 5_000,
  });
  await page.getByTestId("pipeline-run-button").click();
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
