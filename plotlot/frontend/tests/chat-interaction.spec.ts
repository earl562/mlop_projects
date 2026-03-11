import { test, expect } from "@playwright/test";

test.describe("PlotLot Chat Interaction", () => {
  test.setTimeout(180_000);

  test("welcome state renders correctly", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Floating pill nav
    await expect(page.locator("nav").filter({ hasText: "PlotLot" })).toBeVisible();
    await expect(page.getByText("Beta")).toBeVisible();
    await expect(page.getByText("104 municipalities")).toBeVisible();

    // Serif heading
    await expect(page.getByText("Analyze any property")).toBeVisible();
    await expect(page.getByText("in South Florida")).toBeVisible();

    // Input bar
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await expect(input).toBeVisible();

    // Suggestion chips
    await expect(page.getByText("Analyze a property in Miami Gardens")).toBeVisible();
    await expect(page.getByText("Find vacant lots in Miami-Dade")).toBeVisible();

    // Send button disabled when empty
    const sendBtn = page.getByRole("button", { name: "Send message" });
    await expect(sendBtn).toBeDisabled();
  });

  test("dark mode toggle works", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Should start in light mode
    const html = page.locator("html");
    await expect(html).not.toHaveClass(/dark/);

    // Click theme toggle
    const themeToggle = page.locator("nav button").last();
    await themeToggle.click();

    // Should switch to dark mode
    await expect(html).toHaveClass(/dark/);

    // Toggle back
    await themeToggle.click();
    await expect(html).not.toHaveClass(/dark/);
  });

  test("typing enables send button", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    const input = page.getByPlaceholder("Enter an address or ask a question...");
    const sendBtn = page.getByRole("button", { name: "Send message" });

    await expect(sendBtn).toBeDisabled();
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await expect(sendBtn).toBeEnabled();
  });

  test("full analysis pipeline and report", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await page.getByRole("button", { name: "Send message" }).click();

    // Pipeline stepper appears with step counter
    await expect(page.getByText(/Step \d+ of 6/)).toBeVisible({ timeout: 15_000 });

    // Wait for report to load (zoning district appears)
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Report card structure
    await expect(page.getByText("Miami Gardens")).toBeVisible();
    await expect(page.getByText("PDF")).toBeVisible();

    // Section pills
    await expect(page.getByText("DIMENSIONAL STANDARDS")).toBeVisible();

    // Density breakdown with hero number
    await expect(page.getByText("MAX ALLOWABLE UNITS")).toBeVisible();

    // Follow-up chips appear
    await expect(page.getByText("What can I build on this lot?")).toBeVisible();

    // Follow-up input bar
    await expect(page.getByPlaceholder("Ask about this property's zoning...")).toBeVisible();
  });

  test("chat follow-up question", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Run analysis first
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Click a follow-up suggestion chip
    await page.getByText("What can I build on this lot?").click();

    // Should see a chat response (assistant message appears)
    await expect(page.locator('[class*="text-sm"]').filter({ hasText: /build|construct|develop/i })).toBeVisible({
      timeout: 60_000,
    });
  });

  test("chat free-form question", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Run analysis first
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Type a follow-up question in the chat input
    const chatInput = page.getByPlaceholder("Ask about this property's zoning...");
    await chatInput.fill("Can I build a duplex here?");

    const chatSend = page.locator("button[aria-label='Send message']").last();
    await chatSend.click();

    // Should get a response about duplex/multifamily/zoning
    await expect(
      page.getByText(/duplex|single.family|multi|R-1|not permitted|zoning/i).last()
    ).toBeVisible({ timeout: 60_000 });
  });

  test("new analysis resets to welcome state", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Run analysis
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.getByText(/Step \d+ of 6/)).toBeVisible({ timeout: 15_000 });

    // Click "+ New analysis"
    await page.getByText("New analysis").click();

    // Should reset to welcome state
    await expect(page.getByText("Analyze any property")).toBeVisible();
    await expect(page.getByPlaceholder("Enter an address or ask a question...")).toBeVisible();
  });

  test("collapsible sections toggle", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Run analysis
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("4341 NW 183rd St, Miami Gardens, FL 33055");
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // SETBACKS section should be collapsible — click to toggle
    const setbacksPill = page.getByText("SETBACKS");
    if (await setbacksPill.isVisible()) {
      await setbacksPill.click();
      // Content should appear/disappear
      await page.waitForTimeout(300);
    }

    // PROPERTY INTELLIGENCE should be collapsible
    const intelligencePill = page.getByText("PROPERTY INTELLIGENCE");
    if (await intelligencePill.isVisible()) {
      await intelligencePill.click();
      await page.waitForTimeout(300);
    }
  });

  test("mobile viewport renders correctly", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/", { waitUntil: "networkidle" });

    // Nav pill visible and compact
    await expect(page.locator("nav").filter({ hasText: "PlotLot" })).toBeVisible();

    // Heading visible
    await expect(page.getByText("Analyze any property")).toBeVisible();

    // Input and chips visible
    await expect(page.getByPlaceholder("Enter an address or ask a question...")).toBeVisible();

    // 104 municipalities hidden on mobile
    await expect(page.getByText("104 municipalities")).not.toBeVisible();
  });
});
