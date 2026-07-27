import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

import { AUTH_ROLES, capabilitiesForRole } from "../src/lib/auth-roles";
import { assertProductionAuthConfiguration } from "../src/lib/auth-config";

test("each authenticated role exposes only its configured capabilities", async ({ page }) => {
  const matrix = AUTH_ROLES.map((role) => ({
    role,
    capabilities: [...capabilitiesForRole(role)].sort(),
  }));

  await page.setContent(
    `<main>${matrix
      .map(
        ({ role, capabilities }) =>
          `<section data-role="${role}"><h2>${role}</h2><ul>${capabilities
            .map((capability) => `<li>${capability}</li>`)
            .join("")}</ul></section>`,
      )
      .join("")}</main>`,
  );

  await expect(page.locator("[data-role=owner] li")).toHaveCount(6);
  await expect(page.locator("[data-role=admin] li")).toHaveCount(5);
  await expect(page.locator("[data-role=analyst] li")).toHaveText([
    "analysis:run",
    "analysis:view",
  ]);
  await expect(page.locator("[data-role=reviewer] li")).toHaveText([
    "analysis:review",
    "analysis:view",
  ]);
  await expect(page.locator("[data-role=viewer] li")).toHaveText(["analysis:view"]);
});

test("production auth source contains no anonymous test bypass", async ({ page }) => {
  const proxySource = readFileSync("src/proxy.ts", "utf8");
  const middlewareSource = readFileSync("src/middleware.ts", "utf8");

  await page.setContent("<p data-auth-state>protected</p>");

  await expect(page.locator("[data-auth-state]")).toHaveText("protected");
  expect(process.env.PLOTLOT_TEST_AUTH_BYPASS).toBe("0");
  expect(proxySource).not.toContain("PLAYWRIGHT_TESTING");
  expect(proxySource).not.toContain("PLOTLOT_TEST_AUTH_BYPASS");
  expect(middlewareSource).toContain('export { default } from "./proxy"');
});

test("production startup rejects incomplete Clerk configuration", () => {
  expect(() =>
    assertProductionAuthConfiguration({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_local",
    }),
  ).toThrow("Production startup requires complete Clerk configuration");

  expect(() =>
    assertProductionAuthConfiguration({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_local",
      CLERK_SECRET_KEY: "sk_test_local",
    }),
  ).not.toThrow();
});
