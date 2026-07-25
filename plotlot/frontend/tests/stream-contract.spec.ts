import {
  test,
  expect,
  gotoHome,
  runLookupFlow,
  switchToAgent,
  switchToLookup,
} from "./helpers";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

interface CanonicalLeadSample {
  address: string;
  addressHash: string;
  county: "miami-dade" | "broward" | "palm-beach";
  municipality: string;
}

const LEAD_LIST_PATH = process.env.PLOTLOT_BYRIGHT_LEAD_LIST_PATH;
const LEAD_LIST_SHA256 = process.env.PLOTLOT_BYRIGHT_LEAD_LIST_SHA256;
const LAUNCH_COUNTIES = ["miami-dade", "broward", "palm-beach"] as const;

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function loadCanonicalLeadSample(): CanonicalLeadSample[] {
  if (!LEAD_LIST_PATH) {
    return [{
      address: "100 Example St, Miami, FL 33101",
      addressHash: sha256("100 EXAMPLE ST, MIAMI, FL 33101"),
      county: "miami-dade",
      municipality: "Miami",
    }];
  }

  const source = readFileSync(LEAD_LIST_PATH, "utf8");
  const sourceHash = sha256(source);
  if (LEAD_LIST_SHA256 && sourceHash !== LEAD_LIST_SHA256) {
    throw new Error(
      `ByRight lead-list hash mismatch: expected ${LEAD_LIST_SHA256}, received ${sourceHash}`,
    );
  }

  const publicRows: CanonicalLeadSample[] = [];
  const rowPattern =
    /sourceList:\s*"south-florida-public-parcel-list",\s*county:\s*"(miami-dade|broward|palm-beach)",\s*address:\s*"([^"]+)"/g;
  for (const match of source.matchAll(rowPattern)) {
    const county = match[1] as CanonicalLeadSample["county"];
    const address = match[2];
    const municipality = address.split(",")[1]?.trim() || "Unknown";
    publicRows.push({
      address,
      addressHash: sha256(address.trim().toUpperCase()),
      county,
      municipality,
    });
  }

  return LAUNCH_COUNTIES.map((county) => {
    const selected = publicRows
      .filter((row) => row.county === county)
      .sort((left, right) => left.addressHash.localeCompare(right.addressHash))[0];
    if (!selected) {
      throw new Error(`No public canonical lead row found for ${county}`);
    }
    return selected;
  });
}

const CANONICAL_SAMPLE = loadCanonicalLeadSample();
const ADDRESS = CANONICAL_SAMPLE[0].address;

async function submitAgentPrompt(page: Parameters<typeof gotoHome>[0], prompt: string) {
  await gotoHome(page);
  await switchToAgent(page);
  await page.getByTestId("agent-input").fill(prompt);
  await page.getByTestId("send-button").click();
}

async function expectRecoverableAgentError(
  page: Parameters<typeof gotoHome>[0],
  prompt: string,
  expectedError: string,
) {
  await expect(page.getByTestId("report-error")).toHaveCount(1, { timeout: 35_000 });
  await expect(page.getByTestId("report-error")).toContainText(expectedError);
  await expect(page.getByTestId("agent-input")).toBeEnabled();
  await expect(page.getByTestId("assistant-retry")).toBeEnabled();
  await expect(
    page.getByTestId("conversation-scroll").getByText(prompt, { exact: true }),
  ).toHaveCount(1);

  await page.getByTestId("assistant-retry").click();
  await expect(page.getByText("Retry completed.", { exact: true })).toBeVisible({
    timeout: 5_000,
  });
  await expect(page.getByTestId("report-error")).toHaveCount(0);
  await expect(page.getByTestId("agent-input")).toBeEnabled();
  await expect(
    page.getByTestId("conversation-scroll").getByText(prompt, { exact: true }),
  ).toHaveCount(1);
}

test("lookup status-only close yields one recoverable error and enables retry", async ({ page }) => {
  test.info().annotations.push({ type: "allow-missing-terminal-sse" });
  let streamAttempts = 0;
  await page.route("**/api/v1/analyze/stream", async (route) => {
    streamAttempts += 1;
    const body = streamAttempts === 1
      ? `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address..." })}\n\n`
      : `event: error\ndata: ${JSON.stringify({ detail: "Retry reached backend", error_type: "backend_unavailable" })}\n\n`;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
  await page.route("**/health", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ status: "unhealthy" }),
    }));
  await page.route("**/api/v1/analyze", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Sync fallback unavailable" }),
    }));

  await gotoHome(page);
  await runLookupFlow(page, ADDRESS);

  await expect(page.getByTestId("report-error")).toHaveCount(1, { timeout: 5_000 });
  await expect(page.getByTestId("report-error")).toContainText(
    "analysis stream ended before a final result",
  );
  await expect(page.getByTestId("pipeline-stepper")).toHaveCount(0);
  await expect(page.getByTestId("lookup-input")).toBeEnabled();
  await expect(page.getByTestId("report-retry-button")).toBeEnabled();
  await expect(
    page.getByTestId("conversation-scroll").getByText(ADDRESS, { exact: true }),
  ).toHaveCount(1);

  await page.getByTestId("report-retry-button").click();
  await expect(page.getByTestId("report-error")).toHaveCount(1);
  await expect(page.getByTestId("report-error")).toContainText("temporarily offline");
  expect(streamAttempts).toBe(2);
});

test("agent close without terminal yields one recoverable error and retry succeeds", async ({ page }) => {
  test.info().annotations.push({ type: "allow-missing-terminal-sse" });
  let attempts = 0;
  await page.route("**/api/v1/chat", async (route) => {
    attempts += 1;
    const body = attempts === 1
      ? `event: session\ndata: ${JSON.stringify({ session_id: "session-1" })}\n\n`
      : `event: done\ndata: ${JSON.stringify({ full_content: "Retry completed." })}\n\n`;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });

  await gotoHome(page);
  await switchToAgent(page);
  await page.getByTestId("agent-input").fill("Explain the current parcel");
  await page.getByTestId("send-button").click();

  await expect(page.getByTestId("report-error")).toHaveCount(1, { timeout: 5_000 });
  await expect(page.getByTestId("report-error")).toContainText(
    "response stream ended before completion",
  );
  await expect(page.getByTestId("agent-input")).toBeEnabled();
  await expect(page.getByTestId("assistant-retry")).toBeEnabled();
  await expect(
    page
      .getByTestId("conversation-scroll")
      .getByText("Explain the current parcel", { exact: true }),
  ).toHaveCount(1);

  await page.getByTestId("assistant-retry").click();
  await expect(page.getByText("Retry completed.", { exact: true })).toBeVisible();
  await expect(page.getByTestId("agent-input")).toBeEnabled();
  expect(attempts).toBe(2);
});

test("agent abort yields one recoverable error and retry succeeds", async ({ page }) => {
  test.info().annotations.push({ type: "allow-critical-request-failure" });
  test.info().annotations.push({ type: "allow-console-error" });
  let attempts = 0;
  await page.route("**/api/v1/chat", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ full_content: "Retry completed." })}\n\n`,
    });
  });

  const prompt = "Abort contract probe";
  await submitAgentPrompt(page, prompt);
  await expectRecoverableAgentError(page, prompt, "connection was interrupted");
  expect(attempts).toBe(2);
});

test("agent malformed JSON yields one recoverable error and retry succeeds", async ({ page }) => {
  test.info().annotations.push({ type: "allow-missing-terminal-sse" });
  let attempts = 0;
  await page.route("**/api/v1/chat", async (route) => {
    attempts += 1;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: attempts === 1
        ? "event: token\ndata: {not-json}\n\n"
        : `event: done\ndata: ${JSON.stringify({ full_content: "Retry completed." })}\n\n`,
    });
  });

  const prompt = "Malformed stream contract probe";
  await submitAgentPrompt(page, prompt);
  await expectRecoverableAgentError(page, prompt, "sent invalid data");
  expect(attempts).toBe(2);
});

test("agent HTTP failure yields one recoverable error and retry succeeds", async ({ page }) => {
  test.info().annotations.push({ type: "allow-console-error" });
  let attempts = 0;
  await page.route("**/api/v1/chat", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Injected HTTP failure" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ full_content: "Retry completed." })}\n\n`,
    });
  });

  const prompt = "HTTP contract probe";
  await submitAgentPrompt(page, prompt);
  await expectRecoverableAgentError(page, prompt, "Injected HTTP failure");
  expect(attempts).toBe(2);
});

test("agent 30 second idle timeout yields one recoverable error and retry succeeds", async ({ page }) => {
  test.info().annotations.push({ type: "allow-critical-request-failure" });
  test.info().annotations.push({ type: "allow-console-error" });
  let attempts = 0;
  await page.route("**/api/v1/chat", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await new Promise((resolve) => setTimeout(resolve, 31_000));
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: done\ndata: ${JSON.stringify({ full_content: "Too late" })}\n\n`,
      }).catch(() => undefined);
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ full_content: "Retry completed." })}\n\n`,
    });
  });

  const prompt = "Idle contract probe";
  await submitAgentPrompt(page, prompt);
  await expectRecoverableAgentError(page, prompt, "response timed out");
  expect(attempts).toBe(2);
});

test("canonical ByRight lead sample recovers in lookup and agent modes", async ({ page }) => {
  test.skip(!LEAD_LIST_PATH, "Set PLOTLOT_BYRIGHT_LEAD_LIST_PATH for the cross-repo sample gate.");
  test.info().annotations.push({ type: "allow-missing-terminal-sse" });

  const outcomes: Array<{
    addressHash: string;
    county: string;
    municipality: string;
    mode: "lookup" | "agent";
    attempts: number;
    errorCount: number;
    inputEnabled: boolean;
    userMessageCount: number;
  }> = [];

  await page.route("**/api/v1/autocomplete**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ suggestions: [] }),
    }));
  await gotoHome(page);
  await page.evaluate(() => localStorage.clear());

  for (const lead of CANONICAL_SAMPLE) {
    for (const mode of ["lookup", "agent"] as const) {
      let attempts = 0;
      await page.route("**/api/v1/analyze/stream", async (route) => {
        attempts += 1;
        const body = attempts === 1
          ? `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address..." })}\n\n`
          : `event: error\ndata: ${JSON.stringify({ detail: "Canonical sample retry reached backend", error_type: "backend_unavailable" })}\n\n`;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body,
        });
      });

      await page.getByRole("button", { name: /New analysis/ }).first().click();
      if (mode === "lookup") {
        await switchToLookup(page);
      } else {
        await switchToAgent(page);
      }
      const input = page.getByTestId(mode === "lookup" ? "lookup-input" : "agent-input");
      const sendButton = page.getByTestId("send-button");
      for (let attempt = 0; attempt < 3; attempt += 1) {
        await input.fill(lead.address);
        await page.waitForTimeout(150);
        if (
          (await input.inputValue().catch(() => "")) === lead.address &&
          (await sendButton.isEnabled().catch(() => false))
        ) {
          break;
        }
      }
      await expect(input).toHaveValue(lead.address);
      await expect(sendButton).toBeEnabled();
      await sendButton.click();

      await expect(page.getByTestId("report-error")).toHaveCount(1, { timeout: 5_000 });
      await expect(page.getByTestId("pipeline-stepper")).toHaveCount(0);
      await expect(page.getByTestId("report-retry-button")).toBeEnabled();
      await expect(input).toBeEnabled();
      await expect(
        page.getByTestId("conversation-scroll").getByText(lead.address, { exact: true }),
      ).toHaveCount(1);

      await page.getByTestId("report-retry-button").click();
      await expect(page.getByTestId("report-error")).toContainText("temporarily offline");
      await expect(input).toBeEnabled();

      outcomes.push({
        addressHash: lead.addressHash,
        county: lead.county,
        municipality: lead.municipality,
        mode,
        attempts,
        errorCount: await page.getByTestId("report-error").count(),
        inputEnabled: await input.isEnabled(),
        userMessageCount: await page
          .getByTestId("conversation-scroll")
          .getByText(lead.address, { exact: true })
          .count(),
      });
      await page.unroute("**/api/v1/analyze/stream");
    }
  }

  await test.info().attach("canonical-lead-sample.json", {
    body: JSON.stringify({
      sourcePath: LEAD_LIST_PATH,
      sourceSha256: LEAD_LIST_SHA256 || sha256(readFileSync(LEAD_LIST_PATH!, "utf8")),
      selection: "minimum normalized-address SHA-256 per launch county from south-florida-public-parcel-list",
      outcomes,
    }, null, 2),
    contentType: "application/json",
  });

  expect(outcomes).toHaveLength(6);
  expect(outcomes.every((outcome) =>
    outcome.attempts === 2 &&
    outcome.errorCount === 1 &&
    outcome.inputEnabled &&
    outcome.userMessageCount === 1
  )).toBe(true);
});
