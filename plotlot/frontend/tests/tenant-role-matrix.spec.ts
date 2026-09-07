import { expect, test } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";
import { readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createHash } from "node:crypto";

const FRONTEND_BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3003";
const TOKEN_FILE =
  process.env.PLOTLOT_TASK8_TOKEN_FILE ??
  resolve(
    tmpdir(),
    `plotlot-task8-${createHash("sha256").update(resolve(process.cwd())).digest("hex").slice(0, 16)}`,
    "tokens.json",
  );
const RELEASE_FIXTURE = {
  analysisId: "analysis-reviewed",
  revisionId: "revision-reviewed",
  revisionSha256: "235481ade82ae632dd10d09ce5d3ac3c7f3fb731a80bf1825b9a9b44041c0756",
};

type RoleTokens = {
  readonly tenantAAnalyst: string;
  readonly tenantAReviewer: string;
  readonly tenantAViewer: string;
  readonly tenantBAnalyst: string;
};

type BrowserIssues = {
  readonly consoleErrors: string[];
  readonly pageErrors: string[];
  readonly failedRequests: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readRoleTokens(): RoleTokens {
  const permissions = statSync(TOKEN_FILE).mode & 0o777;
  if ((permissions & 0o077) !== 0) {
    throw new Error("Task 8 token file must not be group- or world-readable");
  }

  const parsed: unknown = JSON.parse(readFileSync(TOKEN_FILE, "utf8"));
  if (!isRecord(parsed)) {
    throw new Error("Task 8 token file must be an object");
  }

  const analyst = parsed["tenant_a_analyst"];
  const reviewer = parsed["tenant_a_reviewer"];
  const viewer = parsed["tenant_a_viewer"];
  const tenantBAnalyst = parsed["tenant_b_analyst"];
  if (
    typeof analyst !== "string" ||
    typeof reviewer !== "string" ||
    typeof viewer !== "string" ||
    typeof tenantBAnalyst !== "string"
  ) {
    throw new Error("Task 8 token file has an invalid role-token shape");
  }

  return {
    tenantAAnalyst: analyst,
    tenantAReviewer: reviewer,
    tenantAViewer: viewer,
    tenantBAnalyst,
  };
}

function attachBrowserIssueCapture(page: Page): BrowserIssues {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failedRequests.push(`${response.status()} ${response.url()}`);
    }
  });

  return { consoleErrors, pageErrors, failedRequests };
}

function assertNoBrowserBlockers(issues: BrowserIssues): void {
  expect(issues.consoleErrors).toEqual([]);
  expect(issues.pageErrors).toEqual([]);
  expect(issues.failedRequests).toEqual([]);
}

function requestIdFrom(body: string): string {
  const parsed: unknown = JSON.parse(body);
  if (!isRecord(parsed) || typeof parsed["request_id"] !== "string" || parsed["request_id"].length === 0) {
    throw new Error("Release success response omitted a non-empty request_id");
  }
  return parsed["request_id"];
}

function invalidToken(token: string): string {
  const finalCharacter = token.endsWith("x") ? "y" : "x";
  return `${token.slice(0, -1)}${finalCharacter}`;
}

async function establishSession(
  context: BrowserContext,
  token: string,
): Promise<void> {
  const response = await context.request.post(`${FRONTEND_BASE_URL}/api/local-auth/session`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(204);
}

async function backendRequest(
  context: BrowserContext,
  method: "GET" | "POST" | "DELETE",
  path: string,
  body?: Record<string, unknown>,
) {
  const url = `${FRONTEND_BASE_URL}/api/local-auth/backend${path}`;
  if (body === undefined) {
    return context.request.fetch(url, { method });
  }
  return context.request.fetch(url, { method, data: body });
}

async function frontendRequest(
  context: BrowserContext,
  method: "GET" | "POST" | "PUT",
  path: string,
  body?: Record<string, unknown>,
) {
  const url = `${FRONTEND_BASE_URL}${path}`;
  if (body === undefined) {
    return context.request.fetch(url, { method });
  }
  return context.request.fetch(url, { method, data: body });
}

test.describe("tenant and role browser matrix with production authentication", () => {
  test("Given anonymous and Viewer callers, when they reach connector proxies or spoof the Host header, then the boundary denies access before a connector can run", async ({ browser }) => {
    // Given
    const tokens = readRoleTokens();
    const anonymousContext = await browser.newContext();
    const viewerContext = await browser.newContext();
    const spoofedHostContext = await browser.newContext();
    await establishSession(viewerContext, tokens.tenantAViewer);

    try {
      // When
      const anonymousFal = await frontendRequest(anonymousContext, "GET", "/api/fal/proxy");
      const anonymousGis = await frontendRequest(anonymousContext, "GET", "/api/gis-proxy");
      const anonymousVideo = await frontendRequest(anonymousContext, "POST", "/api/video/generate", {});
      const viewerFal = await frontendRequest(viewerContext, "POST", "/api/fal/proxy", {});
      const viewerVideo = await frontendRequest(viewerContext, "POST", "/api/video/generate", {});
      const spoofedHost = await spoofedHostContext.request.post(
        `${FRONTEND_BASE_URL}/api/local-auth/session`,
        {
          headers: {
            Authorization: `Bearer ${tokens.tenantAAnalyst}`,
            Host: "attacker.invalid",
          },
        },
      );

      // Then
      expect(anonymousFal.status()).toBe(401);
      expect(anonymousGis.status()).toBe(401);
      expect(anonymousVideo.status()).toBe(401);
      expect(viewerFal.status()).toBe(403);
      expect(viewerVideo.status()).toBe(403);
      expect(spoofedHost.status()).toBe(404);
    } finally {
      await Promise.all([
        anonymousContext.close(),
        viewerContext.close(),
        spoofedHostContext.close(),
      ]);
    }
  });

  test("Given distinct Analyst and Reviewer sessions, when the Analyst requests and both attempt release, then self-release is denied and review releases exactly once", async ({ browser }) => {
    // Given
    const tokens = readRoleTokens();
    const analystContext = await browser.newContext();
    const reviewerContext = await browser.newContext();
    await establishSession(analystContext, tokens.tenantAAnalyst);
    await establishSession(reviewerContext, tokens.tenantAReviewer);
    const analystPage = await analystContext.newPage();
    const reviewerPage = await reviewerContext.newPage();
    const analystIssues = attachBrowserIssueCapture(analystPage);
    const reviewerIssues = attachBrowserIssueCapture(reviewerPage);

    try {
      // When
      await analystPage.goto(`${FRONTEND_BASE_URL}/workspace`, { waitUntil: "domcontentloaded" });
      await reviewerPage.goto(`${FRONTEND_BASE_URL}/workspace`, { waitUntil: "domcontentloaded" });
      await expect(analystPage.getByTestId("lookup-input")).toBeVisible();
      await expect(reviewerPage.getByTestId("lookup-input")).toBeVisible();
      const releaseRequest = await backendRequest(analystContext, "POST", "/api/v1/releases", {
        analysis_id: RELEASE_FIXTURE.analysisId,
        revision_id: RELEASE_FIXTURE.revisionId,
        revision_sha256: RELEASE_FIXTURE.revisionSha256,
      });
      expect(releaseRequest.status()).toBe(201);
      const requestId = requestIdFrom(await releaseRequest.text());
      const selfRelease = await backendRequest(
        analystContext,
        "POST",
        `/api/v1/releases/${requestId}/release`,
      );
      const reviewerRelease = await backendRequest(
        reviewerContext,
        "POST",
        `/api/v1/releases/${requestId}/release`,
      );
      const duplicateRelease = await backendRequest(
        reviewerContext,
        "POST",
        `/api/v1/releases/${requestId}/release`,
      );

      // Then
      expect(selfRelease.status()).toBe(403);
      expect(reviewerRelease.status()).toBe(200);
      expect(await reviewerRelease.text()).toContain(RELEASE_FIXTURE.revisionId);
      expect(duplicateRelease.status()).toBe(409);
      await analystPage.reload({ waitUntil: "domcontentloaded" });
      await expect(analystPage.getByTestId("lookup-input")).toBeVisible();
      assertNoBrowserBlockers(analystIssues);
      assertNoBrowserBlockers(reviewerIssues);
    } finally {
      await Promise.all([analystContext.close(), reviewerContext.close()]);
    }
  });

  test("Given a Reviewer session, when it originates an analyst action, then the server denies it without creating a release", async ({ browser }) => {
    // Given
    const tokens = readRoleTokens();
    const reviewerContext = await browser.newContext();
    await establishSession(reviewerContext, tokens.tenantAReviewer);
    const reviewerPage = await reviewerContext.newPage();
    const reviewerIssues = attachBrowserIssueCapture(reviewerPage);

    try {
      // When
      await reviewerPage.goto(`${FRONTEND_BASE_URL}/workspace`, { waitUntil: "domcontentloaded" });
      await expect(reviewerPage.getByTestId("lookup-input")).toBeVisible();
      const reviewerOriginates = await backendRequest(reviewerContext, "POST", "/api/v1/releases", {
        analysis_id: RELEASE_FIXTURE.analysisId,
        revision_id: RELEASE_FIXTURE.revisionId,
        revision_sha256: RELEASE_FIXTURE.revisionSha256,
      });

      // Then
      expect(reviewerOriginates.status()).toBe(403);
      assertNoBrowserBlockers(reviewerIssues);
    } finally {
      await reviewerContext.close();
    }
  });

  test("Given Viewer, Tenant B, unauthenticated, invalid-token, and spoofing attempts, when they use protected routes, then each is denied before disclosure or elevation", async ({ browser }) => {
    // Given
    const tokens = readRoleTokens();
    const viewerContext = await browser.newContext();
    const tenantBContext = await browser.newContext();
    const anonymousContext = await browser.newContext();
    const invalidContext = await browser.newContext();
    await establishSession(viewerContext, tokens.tenantAViewer);
    await establishSession(tenantBContext, tokens.tenantBAnalyst);

    try {
      // When
      const viewerRelease = await backendRequest(viewerContext, "POST", "/api/v1/releases", {
        analysis_id: RELEASE_FIXTURE.analysisId,
        revision_id: RELEASE_FIXTURE.revisionId,
        revision_sha256: RELEASE_FIXTURE.revisionSha256,
      });
      const viewerAdmin = await backendRequest(viewerContext, "GET", "/api/v1/admin/chunks/stats");
      const crossTenant = await backendRequest(
        tenantBContext,
        "GET",
        "/api/v1/workspaces/tenant-a/projects",
      );
      const crossTenantList = await backendRequest(
        tenantBContext,
        "GET",
        "/api/v1/analyses?workspace_id=tenant-a",
      );
      const crossTenantWrite = await backendRequest(tenantBContext, "POST", "/api/v1/analyses", {
        workspace_id: "tenant-a",
        source: "browser-matrix",
      });
      const crossTenantDelete = await backendRequest(
        tenantBContext,
        "DELETE",
        "/api/v1/portfolio/tenant-a-resource",
      );
      const spoof = await backendRequest(viewerContext, "POST", "/api/v1/releases", {
        actor_user_id: "tenant-a-admin",
        role: "admin",
        analysis_id: RELEASE_FIXTURE.analysisId,
        revision_id: RELEASE_FIXTURE.revisionId,
        revision_sha256: RELEASE_FIXTURE.revisionSha256,
      });
      const anonymous = await backendRequest(anonymousContext, "GET", "/api/v1/admin/chunks/stats");
      const invalid = await invalidContext.request.post(`${FRONTEND_BASE_URL}/api/local-auth/session`, {
        headers: { Authorization: `Bearer ${invalidToken(tokens.tenantAAnalyst)}` },
      });

      // Then
      expect(viewerRelease.status()).toBe(403);
      expect(viewerAdmin.status()).toBe(403);
      expect(crossTenant.status()).toBe(403);
      expect(crossTenantList.status()).toBe(403);
      expect(crossTenantWrite.status()).toBe(403);
      expect(crossTenantDelete.status()).toBe(403);
      expect(spoof.status()).toBe(403);
      expect(anonymous.status()).toBe(401);
      expect(invalid.status()).toBe(401);
    } finally {
      await Promise.all([
        viewerContext.close(),
        tenantBContext.close(),
        anonymousContext.close(),
        invalidContext.close(),
      ]);
    }
  });
});
