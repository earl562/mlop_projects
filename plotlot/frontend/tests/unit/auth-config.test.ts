import { describe, expect, it } from "vitest";

import {
  ProductionAuthConfigurationError,
  assertProductionAuthConfiguration,
} from "@/lib/auth-config";

describe("assertProductionAuthConfiguration", () => {
  it("Given production without Clerk keys, when startup is validated, then it fails closed", () => {
    expect(() =>
      assertProductionAuthConfiguration({ NODE_ENV: "production" }),
    ).toThrow(ProductionAuthConfigurationError);
  });

  it("Given production with complete Clerk keys, when startup is validated, then it succeeds", () => {
    expect(() =>
      assertProductionAuthConfiguration({
        NODE_ENV: "production",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_configured",
        CLERK_SECRET_KEY: "sk_test_configured",
      }),
    ).not.toThrow();
  });

  it("Given the explicit Playwright process without Clerk keys, when startup is validated, then it may exercise the public shell", () => {
    expect(() =>
      assertProductionAuthConfiguration({
        NODE_ENV: "production",
        PLAYWRIGHT_TESTING: "1",
      }),
    ).not.toThrow();
  });

  it("Given production with any non-enabled Playwright value, when startup is validated, then it still fails closed", () => {
    expect(() =>
      assertProductionAuthConfiguration({
        NODE_ENV: "production",
        PLAYWRIGHT_TESTING: "0",
      }),
    ).toThrow(ProductionAuthConfigurationError);
  });
});
