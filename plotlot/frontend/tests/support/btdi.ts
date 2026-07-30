import {
  expect,
  Page,
  test as base,
  TestInfo,
} from "@playwright/test";

export interface BrowserDiagnostics {
  consoleErrors: string[];
  pageErrors: string[];
  requestFailures: string[];
  serverErrors: string[];
}

interface BtdiFixtures {
  browserDiagnostics: BrowserDiagnostics;
}

export const test = base.extend<BtdiFixtures>({
  browserDiagnostics: async ({ page }, activateFixture, testInfo) => {
    const diagnostics: BrowserDiagnostics = {
      consoleErrors: [],
      pageErrors: [],
      requestFailures: [],
      serverErrors: [],
    };

    page.on("console", (message) => {
      if (message.type() === "error") {
        diagnostics.consoleErrors.push(message.text());
      }
    });
    page.on("pageerror", (error) => {
      diagnostics.pageErrors.push(error.stack ?? error.message);
    });
    page.on("requestfailed", (request) => {
      const failure = request.failure()?.errorText ?? "unknown failure";
      diagnostics.requestFailures.push(`${request.method()} ${request.url()} - ${failure}`);
    });
    page.on("response", (response) => {
      if (response.status() >= 500) {
        diagnostics.serverErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    await activateFixture(diagnostics);

    await testInfo.attach("browser-diagnostics", {
      body: Buffer.from(JSON.stringify(diagnostics, null, 2)),
      contentType: "application/json",
    });
  },
});

export { expect };

export async function captureVisualState(
  page: Page,
  testInfo: TestInfo,
  stateName: string,
) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({
    path: testInfo.outputPath(`${stateName}.png`),
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
}

export function expectCleanBrowser(diagnostics: BrowserDiagnostics) {
  expect(diagnostics.consoleErrors, "browser console errors").toEqual([]);
  expect(diagnostics.pageErrors, "uncaught browser errors").toEqual([]);
  expect(diagnostics.requestFailures, "failed browser requests").toEqual([]);
  expect(diagnostics.serverErrors, "HTTP 5xx responses").toEqual([]);
}
