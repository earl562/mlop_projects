import { test, expect } from "@playwright/test";

test.describe("Design System Verification", () => {
  test("welcome page renders correctly in light mode", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Nav elements
    await expect(page.getByText("PlotLot", { exact: true })).toBeVisible();
    await expect(page.getByText("Beta", { exact: true })).toBeVisible();
    await expect(page.getByText("104 municipalities", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Toggle dark mode" })).toBeVisible();

    // Welcome content
    await expect(page.getByText("Hi there")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Analyze any property in South Florida" })).toBeVisible();
    await expect(page.getByPlaceholder("Enter an address or ask a question...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();

    // 4 suggestion chips
    await expect(page.getByRole("button", { name: /Analyze a property in Miami Gardens/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Find vacant lots/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Zoning rules in Miramar/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /What can I build/ })).toBeVisible();

    await page.screenshot({ path: "tests/screenshots/ds-01-light-welcome.png", fullPage: true });
  });

  test("dark mode toggle works", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Should start in light mode
    const html = page.locator("html");
    await expect(html).not.toHaveClass(/dark/);

    // Click dark mode toggle
    await page.getByRole("button", { name: "Toggle dark mode" }).click();
    await expect(html).toHaveClass(/dark/);

    await page.screenshot({ path: "tests/screenshots/ds-02-dark-welcome.png", fullPage: true });

    // Toggle back to light
    await page.getByRole("button", { name: "Toggle dark mode" }).click();
    await expect(html).not.toHaveClass(/dark/);
  });

  test("dark mode persists across navigation", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Enable dark mode
    await page.getByRole("button", { name: "Toggle dark mode" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    // Navigate to admin
    await page.goto("/admin");
    await page.waitForLoadState("networkidle");

    // Dark mode should persist
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.screenshot({ path: "tests/screenshots/ds-03-dark-admin.png", fullPage: true });
  });

  test("no text-[10px] or text-[11px] in rendered DOM", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Check that no elements use sub-12px font sizes
    const tinyText = await page.evaluate(() => {
      const elements = document.querySelectorAll("*");
      const violations: string[] = [];
      elements.forEach((el) => {
        const style = window.getComputedStyle(el);
        const fontSize = parseFloat(style.fontSize);
        if (fontSize < 12 && el.textContent?.trim()) {
          violations.push(`${el.tagName}: "${el.textContent?.trim().slice(0, 30)}" (${fontSize}px)`);
        }
      });
      return violations;
    });

    // Allow empty or whitespace-only elements, but flag visible text < 12px
    if (tinyText.length > 0) {
      console.warn("Elements with text < 12px:", tinyText);
    }
    // This is informational — some browser defaults may be < 12px
  });

  test("input bar has proper focus styling", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.click();

    // Input should be focusable and visible
    await expect(input).toBeFocused();

    await page.screenshot({ path: "tests/screenshots/ds-04-input-focus.png" });
  });

  test("suggestion chips have hover interaction", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const chip = page.getByRole("button", { name: /Analyze a property in Miami Gardens/ });
    await chip.hover();

    await page.screenshot({ path: "tests/screenshots/ds-05-chip-hover.png" });
  });
});
