import {
  test as base,
  expect,
  type ConsoleMessage,
  type Page,
  type Request,
  type Response,
} from "@playwright/test";
import { writeFile } from "node:fs/promises";

interface BrowserEvidence {
  console: Array<{ type: string; text: string; location: string }>;
  pageErrors: string[];
  requestFailures: Array<{
    method: string;
    resourceType: string;
    url: string;
    errorText: string;
  }>;
  requests: Array<{
    method: string;
    resourceType: string;
    url: string;
  }>;
  responses: Array<{
    method: string;
    resourceType: string;
    status: number;
    url: string;
  }>;
  sse: Array<{
    url: string;
    status: number;
    terminal: boolean;
    transcript: string;
  }>;
}

const EXPECTED_WARNING_PATTERNS = [
  /Download the React DevTools/i,
  /The resource .* was preloaded using link preload but not used/i,
];

function isUnexpectedConsole(message: ConsoleMessage): boolean {
  if (message.type() === "error") return true;
  if (message.type() !== "warning") return false;
  return !EXPECTED_WARNING_PATTERNS.some((pattern) => pattern.test(message.text()));
}

function isCriticalRequest(request: Request): boolean {
  const resourceType = request.resourceType();
  if (["document", "script", "stylesheet"].includes(resourceType)) return true;
  if (!["fetch", "xhr"].includes(resourceType)) return false;
  return /\/(?:api\/|_next\/)/.test(new URL(request.url()).pathname);
}

function isSseResponse(response: Response): boolean {
  const contentType = response.headers()["content-type"] || "";
  return (
    contentType.includes("text/event-stream") &&
    /\/api\/v1\/(?:analyze\/stream|chat)(?:\?|$)/.test(response.url())
  );
}

function hasTerminalEvent(url: string, transcript: string): boolean {
  if (url.includes("/api/v1/analyze/stream")) {
    return /(?:^|\n)event:\s*(?:result|error)\s*(?:\n|$)/.test(transcript);
  }
  if (url.includes("/api/v1/chat")) {
    return /(?:^|\n)event:\s*(?:done|error)\s*(?:\n|$)/.test(transcript);
  }
  return true;
}

function hasAnnotation(
  annotations: Array<{ type: string; description?: string }>,
  type: string,
): boolean {
  return annotations.some((annotation) => annotation.type === type);
}

async function writeEvidenceFiles(
  page: Page,
  evidence: BrowserEvidence,
  failures: string[],
  outputPath: (name: string) => string,
): Promise<void> {
  const consolePath = outputPath("console.log");
  const networkPath = outputPath("request-response.json");
  const ssePath = outputPath("sse-transcript.log");
  const summaryPath = outputPath("failure-evidence.json");
  const screenshotPath = outputPath("failure.png");
  const consoleTranscript = [
    ...evidence.console.map(
      (entry) => `[${entry.type}] ${entry.text} ${entry.location}`.trim(),
    ),
    ...evidence.pageErrors.map((entry) => `[pageerror] ${entry}`),
  ].join("\n") || "[no browser console or page errors captured]\n";
  const sseTranscript = evidence.sse
    .map(
      (entry) =>
        `URL: ${entry.url}\nSTATUS: ${entry.status}\nTERMINAL: ${entry.terminal}\n${entry.transcript}`,
    )
    .join("\n\n---\n\n") || "[no PlotLot SSE responses captured]\n";

  await Promise.all([
    writeFile(consolePath, consoleTranscript, "utf8"),
    writeFile(
      networkPath,
      JSON.stringify(
        {
          requests: evidence.requests,
          responses: evidence.responses,
          requestFailures: evidence.requestFailures,
        },
        null,
        2,
      ),
      "utf8",
    ),
    writeFile(ssePath, sseTranscript, "utf8"),
    writeFile(
      summaryPath,
      JSON.stringify({ failures, evidence }, null, 2),
      "utf8",
    ),
    page.screenshot({ path: screenshotPath, fullPage: true }),
  ]);
}

export const test = base.extend({
  page: async ({ page }, runFixture, testInfo) => {
    const evidence: BrowserEvidence = {
      console: [],
      pageErrors: [],
      requestFailures: [],
      requests: [],
      responses: [],
      sse: [],
    };
    const failures: string[] = [];
    const pendingResponses = new Set<Promise<void>>();

    await page.addInitScript(() => {
      window.addEventListener("unhandledrejection", (event) => {
        const detail =
          event.reason instanceof Error
            ? event.reason.stack || event.reason.message
            : String(event.reason);
        console.error(`[unhandledrejection] ${detail}`);
      });
    });

    page.on("console", (message) => {
      const location = message.location();
      evidence.console.push({
        type: message.type(),
        text: message.text(),
        location: location.url
          ? `${location.url}:${location.lineNumber}:${location.columnNumber}`
          : "",
      });
      if (
        isUnexpectedConsole(message) &&
        !hasAnnotation(testInfo.annotations, "allow-console-error")
      ) {
        failures.push(`Unexpected console ${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => {
      const detail = error.stack || error.message;
      evidence.pageErrors.push(detail);
      failures.push(`Uncaught page error: ${error.message}`);
    });
    page.on("request", (request) => {
      evidence.requests.push({
        method: request.method(),
        resourceType: request.resourceType(),
        url: request.url(),
      });
    });
    page.on("requestfailed", (request) => {
      const errorText = request.failure()?.errorText || "unknown request failure";
      evidence.requestFailures.push({
        method: request.method(),
        resourceType: request.resourceType(),
        url: request.url(),
        errorText,
      });
      if (
        isCriticalRequest(request) &&
        !hasAnnotation(testInfo.annotations, "allow-critical-request-failure")
      ) {
        failures.push(`Critical request failed: ${request.method()} ${request.url()} (${errorText})`);
      }
    });
    page.on("response", (response) => {
      const request = response.request();
      evidence.responses.push({
        method: request.method(),
        resourceType: request.resourceType(),
        status: response.status(),
        url: response.url(),
      });
      if (!isSseResponse(response)) return;

      const capture = response
        .text()
        .then((transcript) => {
          const terminal = hasTerminalEvent(response.url(), transcript);
          evidence.sse.push({
            url: response.url(),
            status: response.status(),
            terminal,
            transcript,
          });
          if (
            response.ok() &&
            !terminal &&
            !hasAnnotation(testInfo.annotations, "allow-missing-terminal-sse")
          ) {
            failures.push(`SSE response closed without a terminal event: ${response.url()}`);
          }
        })
        .catch((error: unknown) => {
          const detail = error instanceof Error ? error.message : String(error);
          failures.push(`Could not retain SSE response body for ${response.url()}: ${detail}`);
        })
        .finally(() => pendingResponses.delete(capture));
      pendingResponses.add(capture);
    });

    await runFixture(page);
    await Promise.allSettled([...pendingResponses]);

    const testAlreadyFailed = testInfo.status !== testInfo.expectedStatus;
    if (testAlreadyFailed || failures.length > 0) {
      await writeEvidenceFiles(
        page,
        evidence,
        failures,
        (name) => testInfo.outputPath(name),
      );
    }

    if (failures.length > 0) {
      throw new Error(`Browser evidence gate failed:\n${failures.join("\n")}`);
    }
  },
});

export { expect };
