import { test, expect, type APIRequestContext } from "@playwright/test";
import { gotoHome, switchToAgent } from "./helpers";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const LIVE_PROMPT =
  process.env.PLOTLOT_LIVE_AGENT_PROMPT ??
  "Use the run_deal_analysis tool with source_mode live and analysis_type acquisition_memo for 623 4TH ST, West Palm Beach, FL 33401. This is a ByRight lead-list acceptance test. Do not substitute fixture data.";

interface AgentReadiness {
  ready: boolean;
  reason: string;
}

interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

async function getAgentReadiness(request: APIRequestContext): Promise<AgentReadiness> {
  try {
    const response = await request.get(`${API_BASE}/health`, { timeout: 5_000 });
    if (!response.ok()) {
      return {
        ready: false,
        reason: `Backend /health returned HTTP ${response.status()} at ${API_BASE}`,
      };
    }

    const body = (await response.json()) as Record<string, unknown>;
    const capabilities = body.capabilities as Record<string, unknown> | undefined;
    const capabilityDetails = body.capability_details as Record<string, unknown> | undefined;
    const agentDetail = capabilityDetails?.agent_chat_ready as Record<string, unknown> | undefined;
    const detailReady = agentDetail?.ready;
    const capabilityReady = capabilities?.agent_chat_ready;
    const ready =
      typeof detailReady === "boolean"
        ? detailReady
        : typeof capabilityReady === "boolean"
          ? capabilityReady
          : false;

    return {
      ready,
      reason: ready
        ? "Backend reports agent_chat_ready"
        : String(agentDetail?.reason ?? "Backend does not report agent_chat_ready"),
    };
  } catch (error) {
    return {
      ready: false,
      reason: `Backend /health was not reachable at ${API_BASE}: ${
        error instanceof Error ? error.message : String(error)
      }`,
    };
  }
}

function parseSse(raw: string): SseEvent[] {
  return raw
    .split(/\n\n+/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .map((chunk) => {
      const lines = chunk.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event: "));
      const dataLine = lines.find((line) => line.startsWith("data: "));
      const event = eventLine?.slice("event: ".length).trim() ?? "message";
      const rawData = dataLine?.slice("data: ".length).trim() ?? "{}";
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(rawData) as Record<string, unknown>;
      } catch {
        data = { raw: rawData };
      }
      return { event, data };
    });
}

test.describe("live served PlotLot agent", () => {
  test.skip(
    process.env.PLOTLOT_LIVE_AGENT_E2E !== "1",
    "Set PLOTLOT_LIVE_AGENT_E2E=1 to run the credential-backed live agent E2E lane.",
  );

  let readiness: AgentReadiness = {
    ready: false,
    reason: "Readiness preflight has not run",
  };

  test.beforeAll(async ({ request }) => {
    readiness = await getAgentReadiness(request);
  });

  test("served frontend streams a real backend agent response", async ({ page }) => {
    expect(readiness.ready, readiness.reason).toBe(true);

    await gotoHome(page);
    await switchToAgent(page);

    await page.getByTestId("agent-input").fill(LIVE_PROMPT);
    const chatResponsePromise = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/v1/chat",
      { timeout: 30_000 },
    );
    await page.getByTestId("send-button").click();

    const log = page.getByRole("log", { name: "Analysis conversation" });
    await expect(log).toContainText(LIVE_PROMPT, { timeout: 15_000 });

    const chatResponse = await chatResponsePromise;
    expect(chatResponse.ok(), `/api/v1/chat returned HTTP ${chatResponse.status()}`).toBe(true);

    const rawSse = await chatResponse.text();
    const events = parseSse(rawSse);
    const eventNames = events.map((event) => event.event);
    expect(eventNames).toContain("session");
    expect(eventNames).toContain("done");
    expect(eventNames, rawSse).not.toContain("error");

    const doneEvent = events.find((event) => event.event === "done");
    const fullContent = String(doneEvent?.data.full_content ?? "").trim();
    expect(fullContent.length, rawSse).toBeGreaterThan(8);
    expect(fullContent).toMatch(/623 4TH ST/i);
    expect(fullContent).toMatch(/NWD-R/i);
    expect(fullContent).toMatch(/\b2\s+(?:by-right\s+)?units?\b|\bmax(?:imum)?\s+units?:?\s*2\b/i);
    expect(fullContent).toMatch(/\$470,?000/);
    expect(fullContent).toMatch(/\$196,?000/);
    expect(fullContent).not.toMatch(/recommended offer:\s*\*{0,2}\$0/i);
    expect(fullContent).not.toMatch(
      /dimensional standards are missing|no comps found|cannot be calculated/i,
    );

    const visiblePrefix = fullContent.replace(/[`*_#]/g, "").slice(0, 40);
    await expect(log).toContainText(visiblePrefix, {
      timeout: 90_000,
    });
    await expect(log).not.toContainText(/Chat is temporarily unavailable|Error:/i);
  });
});
