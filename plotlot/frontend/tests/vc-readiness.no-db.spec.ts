import {
  test,
  expect,
  gotoHome,
  stubAgentChatErrorSse,
  switchToAgent,
  switchToLookup,
} from "./helpers";

test.describe("VC readiness no-db walkthrough", () => {
  test("captures key UI states with stubs @vc @no-db", async ({ page }, testInfo) => {
    await gotoHome(page);
    await page.screenshot({
      path: testInfo.outputPath("01-lookup-welcome.png"),
      fullPage: true,
      caret: "initial",
    });

    // Exercise the direct lookup flow without requiring any backend dependencies.
    const address = "7940 Plantation Blvd, Miramar, FL 33023";
    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");

    await page.route("**/api/v1/autocomplete**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ suggestions: [] }),
      }),
    );
    await page.route("**/api/v1/analyze/stream", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address...", complete: false })}\n\n`,
          `event: status\ndata: ${JSON.stringify({ step: "zoning", message: "Loading zoning context...", complete: false })}\n\n`,
          `event: error\ndata: ${JSON.stringify({ detail: "Recorded demo backend response", error_type: "backend_unavailable" })}\n\n`,
        ].join(""),
      });
    });

    // Avoid hydration races: ensure the controlled value is set before submitting.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await input.fill(address);
      if ((await input.inputValue().catch(() => "")) === address) break;
      await page.waitForTimeout(150);
    }

    await expect(input).toHaveValue(address, { timeout: 10_000 });
    await expect(sendButton).toBeEnabled({ timeout: 10_000 });
    await sendButton.click();
    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: testInfo.outputPath("02-lookup-terminal-response.png"),
      fullPage: true,
      caret: "initial",
    });

    await expect(page.getByText(/analysis backend is temporarily offline/i)).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("03-lookup-recovery.png"),
      fullPage: true,
      caret: "initial",
    });

    await switchToAgent(page);
    await expect(page.getByTestId("agent-input")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("05-agent-welcome.png"),
      fullPage: true,
      caret: "initial",
    });

    await stubAgentChatErrorSse(page, "LLM credentials missing (stubbed for demo)");
    await page.getByTestId("agent-input").fill("What can I build here?");
    await page.getByTestId("send-button").click();
    await expect(
      page.getByText("LLM credentials missing (stubbed for demo)"),
    ).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: testInfo.outputPath("05-agent-error.png"),
      fullPage: true,
      caret: "initial",
    });

    // Switching back should not leak any hidden gating UI into the next session.
    await switchToLookup(page);
    await expect(page.getByTestId("deal-type-selector")).toHaveCount(0);
    await expect(page.getByTestId("pipeline-approval-card")).toHaveCount(0);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("06-lookup-after-switch-back.png"),
      fullPage: true,
      caret: "initial",
    });
  });
});
