import { describe, expect, it } from "vitest";

import { declaredTooLarge } from "@/lib/limits";

describe("request limits", () => {
  it("refuses a body declared larger than the limit", () => {
    const req = (length?: string) =>
      new Request("http://x/api", { method: "POST", headers: length ? { "content-length": length } : {} });
    expect(declaredTooLarge(req("100"), 2000)).toBe(false);
    expect(declaredTooLarge(req("5000"), 2000)).toBe(true);
    expect(declaredTooLarge(req("abc"), 2000)).toBe(true);
    expect(declaredTooLarge(req(), 2000)).toBe(false);
  });
});
