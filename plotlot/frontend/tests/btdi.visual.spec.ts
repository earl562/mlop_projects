import {
  captureVisualState,
  expect,
  expectCleanBrowser,
  test,
} from "./support/btdi";
import { stubAgentChatSse } from "./helpers";

test.describe("Build Test Debug Iterate visual contract", () => {
  test("public homepage", async ({ page, browserDiagnostics }, testInfo) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("public-homepage")).toBeVisible();
    await expect(page.getByRole("heading", { name: "See What Fits." })).toBeVisible();
    await captureVisualState(page, testInfo, "public-homepage");
    expectCleanBrowser(browserDiagnostics);
  });

  test("analysis console", async ({ page, browserDiagnostics }, testInfo) => {
    await page.goto("/analyze", { waitUntil: "domcontentloaded" });

    const console = page.getByRole("region", { name: "PlotLot agent console" });
    const composer = page.getByTestId("agent-input");

    await expect(console).toBeVisible();
    await expect(composer).toBeVisible();
    await expect(page.getByTestId("analyze-computer-card")).toBeVisible();

    const consoleBox = await console.boundingBox();
    const composerBox = await composer.boundingBox();
    const viewport = page.viewportSize();
    expect(consoleBox, "agent console has measurable layout bounds").not.toBeNull();
    expect(composerBox, "agent composer has measurable layout bounds").not.toBeNull();
    expect(viewport, "browser viewport is available").not.toBeNull();
    expect(consoleBox!.y, "agent console starts in the first viewport").toBeLessThan(
      viewport!.height,
    );
    expect(composerBox!.y, "agent composer is usable without a full-page scroll").toBeLessThan(
      viewport!.height,
    );

    await captureVisualState(page, testInfo, "analysis-console");
    expectCleanBrowser(browserDiagnostics);
  });

  test("analysis console preserves blocked evaluation state", async ({
    page,
    browserDiagnostics,
  }, testInfo) => {
    await stubAgentChatSse(page, {
      fullContent: [
        "## Evaluation blocked",
        "",
        "The property cannot be evaluated from the data currently available.",
        "No valuation or offer recommendation was produced.",
        "",
        "### Missing required data",
        "- `official_dimensional_standards`",
        "- `deterministic_feasibility`",
      ].join("\n"),
      toolName: "run_deal_analysis",
      toolMessage: "Running grounded deal analysis...",
      toolResultMessage: "Required zoning and underwriting inputs are missing.",
      toolStatus: "blocked",
    });
    await page.goto("/analyze", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    await page.getByTestId("agent-input").fill("Evaluate 623 4TH ST");
    const sendButton = page.getByRole("button", { name: "Send" });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    await expect(page.getByRole("heading", { name: "Evaluation blocked" })).toBeVisible();
    await expect(
      page.getByTestId("agent-session-sidebar").getByText("Evaluation blocked", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByTestId("analyze-status-card").getByText("Needs data", { exact: true }),
    ).toBeVisible();
    await expect(
      page
        .getByTestId("analyze-status-card")
        .getByText("Blocked run deal analysis", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Latest analysis complete", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Running grounded deal analysis...", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/^Running\b/i)).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
      "blocked analysis has no horizontal clipping or overflow",
    ).toBe(true);
    await captureVisualState(page, testInfo, "analysis-console-blocked");
    expectCleanBrowser(browserDiagnostics);
  });

  test("lookup workspace", async ({ page, browserDiagnostics }, testInfo) => {
    await page.goto("/workspace?mode=lookup", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByRole("button", { name: "Lookup" })).toBeVisible();
    await captureVisualState(page, testInfo, "lookup-workspace");
    expectCleanBrowser(browserDiagnostics);
  });

  test("agent workspace", async ({ page, browserDiagnostics }, testInfo) => {
    await page.goto("/workspace?mode=agent", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("agent-input")).toBeVisible();
    await expect(page.getByRole("button", { name: "Agent" })).toBeVisible();
    await captureVisualState(page, testInfo, "agent-workspace");
    expectCleanBrowser(browserDiagnostics);
  });
});
