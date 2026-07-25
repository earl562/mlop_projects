/**
 * Contract test for vitest jsdom environment (slice 0.3).
 *
 * Pins that localStorage is available in the test environment. jsdom 27 throws
 * "SecurityError: localStorage is not available for opaque origins" when the
 * page loads with no URL (opaque origin). The vitest config must set
 * environmentOptions.jsdom.url so the origin is non-opaque.
 *
 * Without this, tests/ui/analyze-shell.test.tsx::beforeEach calls
 * localStorage.clear() and throws "Cannot read properties of undefined
 * (reading 'clear')" — blocking the entire frontend gate.
 *
 * Regression guard: if anyone removes the jsdom url config, this test fails
 * immediately instead of mysteriously breaking analyze-shell.
 */
import { describe, it, expect } from "vitest";

describe("vitest jsdom environment", () => {
  it("provides localStorage (non-opaque origin)", () => {
    expect(typeof localStorage).toBe("object");
    expect(typeof localStorage.clear).toBe("function");
  });

  it("supports localStorage round-trip", () => {
    localStorage.setItem("plotlot-test-key", "value");
    expect(localStorage.getItem("plotlot-test-key")).toBe("value");
    localStorage.removeItem("plotlot-test-key");
    expect(localStorage.getItem("plotlot-test-key")).toBeNull();
  });
});
