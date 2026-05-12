import { test, expect, type Locator, type Page } from "@playwright/test";

import { designReferenceAlts, logoReference } from "../src/app/plotlot-reference-data";

async function gotoWelcome(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Plotlot", { exact: true }).first()).toBeVisible();
}

async function expectCompactHero(heading: Locator) {
  await expect(heading).toBeVisible();

  const metrics = await heading.evaluate((node) => {
    const el = node as HTMLElement;
    const style = window.getComputedStyle(el);
    const lineHeight = Number.parseFloat(style.lineHeight);
    const rect = el.getBoundingClientRect();
    const lineCount =
      Number.isFinite(lineHeight) && lineHeight > 0
        ? Math.round(rect.height / lineHeight)
        : el.getClientRects().length;

    return {
      lineCount,
      width: rect.width,
      fontSize: Number.parseFloat(style.fontSize),
    };
  });

  expect(metrics.width).toBeGreaterThan(280);
  expect(metrics.fontSize).toBeGreaterThan(40);
  expect(metrics.lineCount).toBeLessThanOrEqual(3);
}

test.describe("Plotlot marketing and workspace surfaces", () => {
  test("home is a live coded landing page with a clear workspace entry", async ({ page }, testInfo) => {
    await gotoWelcome(page);

    await expect(page.getByRole("link", { name: "Analyze a Lot" }).first()).toHaveAttribute("href", "/workspace");
    await expect(page.locator(".coded-hero-visual")).toBeVisible();
    await expect(page.locator(".hero-aerial-panel img")).toBeVisible();
    await expect(page.getByRole("img", { name: designReferenceAlts[0] })).toHaveCount(0);

    const heading = page.getByRole("heading", { name: /See What Fits\./ });
    await expectCompactHero(heading);
    await expect(page.getByRole("link", { name: "View Demo" })).toHaveAttribute("href", "#product");
    await expect(page.getByRole("link", { name: "Explore the Product" })).toHaveAttribute("href", "/workspace");

    await page.screenshot({ path: testInfo.outputPath("ds-01-live-home.png"), fullPage: true });
  });

  test("workspace route restores the interactive analysis surface", async ({ page }) => {
    await page.goto("/workspace");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: "Analyze any property in the US" })).toBeVisible();
    await expect(page.getByPlaceholder("Enter a property address...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Lookup" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Agent" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
    await expect(page.getByText("Houston, TX")).toBeVisible();
    await expect(page.getByText("Atlanta, GA")).toBeVisible();
    await expect(page.getByText("Miami Gardens, FL")).toBeVisible();
    await expect(page.getByText("PlotLot analyzes zoning, density, comps & pro forma for any US property")).toBeVisible();
    await expect(page.getByTestId("workspace-status-card")).toHaveCount(0);
    await expect(page.getByTestId("workspace-plan-card")).toHaveCount(0);
    await expect(page.getByTestId("workspace-evidence-card")).toHaveCount(0);
    await expect(page.getByTestId("workspace-report-card")).toHaveCount(0);
  });

  test("primary nav anchors target the live landing-page sections", async ({ page }) => {
    await gotoWelcome(page);

    await expect(page.getByRole("link", { name: "Product" }).first()).toHaveAttribute("href", "#product");
    await expect(page.getByRole("link", { name: "Solutions" }).first()).toHaveAttribute("href", "#solutions");
    await expect(page.getByRole("link", { name: "Resources" }).first()).toHaveAttribute("href", "#workflow");
    await expect(page.getByRole("link", { name: "Pricing" }).first()).toHaveAttribute("href", "#pricing");
    await expect(page.getByRole("link", { name: "About" }).first()).toHaveAttribute("href", "#proof");

    await expect(page.getByRole("heading", { name: "Trusted for faster diligence." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Everything needed to evaluate a lot." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "A clearer view of the site." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "From address to answer." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Built for land decisions." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What teams say." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Start with one lot." })).toBeVisible();
  });

  test("reference gallery route preserves the original framed comparison view", async ({ page }) => {
    await page.goto("/reference");
    await page.waitForLoadState("networkidle");

    for (const alt of designReferenceAlts) {
      await expect(page.getByRole("img", { name: alt })).toBeVisible();
    }
    await expect(page.getByRole("img", { name: logoReference.alt })).toBeVisible();
  });
});
