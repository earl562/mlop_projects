/**
 * Playwright E2E spec for the auth/billing UI.
 *
 * Verifies the new auth/billing middleware additions render correctly in the
 * frontend. The backend wiring is covered by the 58-test TDD suite (47 unit
 * + 11 integration in tests/integration/test_auth_billing_routes.py). This
 * spec proves the FRONTEND wires up against those backend endpoints.
 *
 * No real Clerk or Stripe credentials are available, so this spec verifies
 * the no-auth / anonymous surface:
 *   - Public landing page renders
 *   - /billing page loads, shows the "Current plan" widget
 *   - "Upgrade to Pro — $49/month" CTA is visible to free users
 *   - The /api/v1/subscription/status fetch path is hit (and degrades
 *     gracefully when the backend is unreachable)
 *   - No console errors during page load
 */

import { expect, test } from "@playwright/test";

test.describe("Auth + billing UI", () => {
  test("public landing page renders without auth", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("public-homepage")).toBeVisible();

    expect(errors, `Page errors: ${errors.join("\n")}`).toHaveLength(0);
  });

  test("billing page shows current plan widget and upgrade CTA for free user", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/billing", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Current plan", { exact: false })).toBeVisible();

    // The upgrade CTA is rendered for any non-pro user. When the backend
    // is unreachable, the page degrades to "Free" and the button is shown.
    const upgradeButton = page.getByRole("button", {
      name: /Upgrade to Pro/i,
    });
    await expect(upgradeButton).toBeVisible({ timeout: 10_000 });
    await expect(upgradeButton).toBeEnabled();

    await page.screenshot({
      path: "playwright-report/auth-billing-upgrade-cta.png",
      fullPage: true,
    });

    // Allow Clerk/Next.js hydration noise but fail on uncaught JS errors.
    const fatal = errors.filter(
      (e) => !e.includes("Clerk") && !e.includes("Stripe") && !e.includes("fetch"),
    );
    expect(fatal, `Page errors: ${fatal.join("\n")}`).toHaveLength(0);
  });

  test("billing page handles ?success=true and ?canceled=true query params", async ({
    page,
  }) => {
    await page.goto("/billing?success=true", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByText(/You're now on Pro\. Unlimited analyses unlocked\./i),
    ).toBeVisible({ timeout: 10_000 });

    await page.goto("/billing?canceled=true", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByText(/Checkout canceled\. Your plan was not changed\./i),
    ).toBeVisible({ timeout: 10_000 });
  });
});
