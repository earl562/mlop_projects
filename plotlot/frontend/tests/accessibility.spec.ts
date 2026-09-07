import { expect, test } from "./fixtures";

const VIEWPORTS = [
  { label: "mobile", width: 375, height: 800 },
  { label: "tablet", width: 768, height: 900 },
  { label: "desktop", width: 1280, height: 720 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`${viewport.label} ${viewport.width}px exposes named landmarks and controls`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Analyze a Lot" }).first(),
    ).toBeVisible();

    await page.goto("/workspace", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByTestId("lookup-input")).toHaveAccessibleName(/address/i);
    await expect(page.getByTestId("send-button")).toHaveAccessibleName(
      /send message/i,
    );
    await page.waitForLoadState("networkidle");

    const unnamedButtons = await page.locator("button").evaluateAll((buttons) =>
      buttons
        .filter(
          (button) =>
            !button.getAttribute("aria-label") && !button.textContent?.trim(),
        )
        .map((button) => button.outerHTML),
    );
    expect(unnamedButtons).toEqual([]);

    await page.screenshot({
      path: testInfo.outputPath(`accessibility-${viewport.label}.png`),
      fullPage: true,
      caret: "initial",
    });
  });
}
