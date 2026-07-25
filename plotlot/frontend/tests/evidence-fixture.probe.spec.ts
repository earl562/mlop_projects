import { test } from "./fixtures";

test.describe("browser evidence fixture probes", () => {
  test.skip(
    process.env.PLOTLOT_EVIDENCE_PROBE !== "1",
    "Run explicitly to prove the failure evidence fixture.",
  );

  test("pageerror", async ({ page }) => {
    await page.setContent("<main>pageerror evidence probe</main>");
    await page.evaluate(() => {
      setTimeout(() => {
        throw new Error("injected pageerror");
      }, 0);
    });
    await page.waitForTimeout(100);
  });

  test("console error", async ({ page }) => {
    await page.setContent("<main>console error evidence probe</main>");
    await page.evaluate(() => console.error("injected console error"));
  });

  test("console warning", async ({ page }) => {
    await page.setContent("<main>console warning evidence probe</main>");
    await page.evaluate(() => console.warn("injected console warning"));
  });

  test("hydration error", async ({ page }) => {
    await page.setContent("<main>hydration error evidence probe</main>");
    await page.evaluate(() =>
      console.error("Hydration failed because the server rendered HTML did not match"),
    );
  });

  test("unhandled rejection", async ({ page }) => {
    await page.setContent("<main>unhandled rejection evidence probe</main>");
    await page.evaluate(() => {
      void Promise.reject(new Error("injected unhandled rejection"));
    });
    await page.waitForTimeout(100);
  });

  test("critical request failure", async ({ page }) => {
    await page.route("**/api/v1/evidence-probe", (route) => route.abort("failed"));
    await page.setContent("<main>critical request evidence probe</main>");
    await page.evaluate(async () => {
      await fetch("http://localhost:8000/api/v1/evidence-probe").catch(() => undefined);
    });
  });

  test("missing terminal SSE", async ({ page }) => {
    await page.route("**/api/v1/chat", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: `event: session\ndata: ${JSON.stringify({ session_id: "probe" })}\n\n`,
      }));
    await page.setContent("<main>missing terminal SSE evidence probe</main>");
    await page.evaluate(async () => {
      await fetch("http://localhost:8000/api/v1/chat", { method: "POST" });
    });
  });
});
