import { describe, expect, it } from "vitest";

import { safeExternalHref } from "../../src/lib/safeExternalUrl";

describe("safeExternalHref", () => {
  it("allows absolute http and https URLs", () => {
    expect(safeExternalHref("https://example.test/parcel?id=1")).toBe(
      "https://example.test/parcel?id=1",
    );
    expect(safeExternalHref("http://example.test/zoning")).toBe(
      "http://example.test/zoning",
    );
  });

  it("rejects non-web and malformed source references", () => {
    expect(safeExternalHref("javascript:alert(1)")).toBeNull();
    expect(safeExternalHref("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeExternalHref("raw://zoning/evidence-zoning")).toBeNull();
    expect(safeExternalHref("/relative/path")).toBeNull();
    expect(safeExternalHref("not a url")).toBeNull();
  });
});
