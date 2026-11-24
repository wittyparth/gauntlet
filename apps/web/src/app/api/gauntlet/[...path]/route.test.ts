import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "gk_test" }) }) }));

import { GET } from "./route";

const call = (path: string[]) =>
  GET(new NextRequest("http://web/api/gauntlet/v1/x"), { params: Promise.resolve({ path }) });

afterEach(() => vi.unstubAllGlobals());

describe("gauntlet proxy", () => {
  it("never forwards a path that climbs out of /v1", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const path of [["v1", "..", "healthz"], ["v1", ".", "runs"], ["v1", "a/../../healthz"], ["v1", "a\\b"]]) {
      expect((await call(path)).status).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a normal path with the cookie key", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    expect((await call(["v1", "runs"])).status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/v1\/runs$/);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer gk_test");
  });
});
