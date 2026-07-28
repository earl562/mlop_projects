import { describe, expect, it } from "vitest";

import {
  localIntegrationModeEnabled,
  localIntegrationRequestHasTrustedLoopbackHost,
} from "@/lib/local-integration-auth";

describe("localIntegrationModeEnabled", () => {
  it("Given a production environment, when the local flag is set, then local integration remains disabled", () => {
    // Given
    const environment = {
      NODE_ENV: "production",
      PLOTLOT_LOCAL_AUTH_INTEGRATION: "1",
      PLOTLOT_LOCAL_AUTH_TEST_ONLY: "1",
    };

    // When
    const enabled = localIntegrationModeEnabled(environment);

    // Then
    expect(enabled).toBe(false);
  });

  it("Given a deployed environment, when the local flag is set, then local integration remains disabled", () => {
    // Given
    const environment = {
      NODE_ENV: "development",
      PLOTLOT_LOCAL_AUTH_INTEGRATION: "1",
      PLOTLOT_LOCAL_AUTH_TEST_ONLY: "1",
      VERCEL: "1",
    };

    // When
    const enabled = localIntegrationModeEnabled(environment);

    // Then
    expect(enabled).toBe(false);
  });

  it("Given local development without the test-only consent, when the local flag is set, then local integration remains disabled", () => {
    // Given
    const environment = {
      NODE_ENV: "development",
      PLOTLOT_LOCAL_AUTH_INTEGRATION: "1",
    };

    // When
    const enabled = localIntegrationModeEnabled(environment);

    // Then
    expect(enabled).toBe(false);
  });

  it("Given local development with test-only consent, when both local flags are set, then local integration is enabled", () => {
    // Given
    const environment = {
      NODE_ENV: "development",
      PLOTLOT_LOCAL_AUTH_INTEGRATION: "1",
      PLOTLOT_LOCAL_AUTH_TEST_ONLY: "1",
    };

    // When
    const enabled = localIntegrationModeEnabled(environment);

    // Then
    expect(enabled).toBe(true);
  });
});

describe("localIntegrationRequestHasTrustedLoopbackHost", () => {
  it("Given a non-loopback request URL, when local integration inspects the request, then it rejects it", () => {
    // Given
    const request = new Request("http://connector.example.invalid/api/local-auth/session");

    // When
    const trusted = localIntegrationRequestHasTrustedLoopbackHost(request);

    // Then
    expect(trusted).toBe(false);
  });

  it("Given a spoofed Host header, when local integration inspects a non-loopback request URL, then it rejects it", () => {
    // Given
    const request = new Request("http://127.0.0.1:3003/api/local-auth/session", {
      headers: { Host: "connector.example.invalid" },
    });

    // When
    const trusted = localIntegrationRequestHasTrustedLoopbackHost(request);

    // Then
    expect(trusted).toBe(false);
  });
});
