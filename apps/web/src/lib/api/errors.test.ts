import { describe, expect, it } from "vitest";

import { ApiError, parseErrorBody } from "./errors";

describe("parseErrorBody", () => {
  it("parses the contract envelope", () => {
    const e = parseErrorBody(404, {
      error: { code: "not_found", message: "run 'x' not found", detail: null },
    });
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.message]).toEqual([404, "not_found", "run 'x' not found"]);
  });
  it("handles FastAPI validation bodies", () => {
    expect(parseErrorBody(422, { detail: [{ msg: "bad" }] }).code).toBe("validation_error");
  });
  it("falls back on garbage", () => {
    expect(parseErrorBody(500, null).message).toContain("500");
  });
});
