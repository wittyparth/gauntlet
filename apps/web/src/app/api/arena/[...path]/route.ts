import type { NextRequest } from "next/server";

/** The arena is a separate service with no accounts: this proxy forwards `/arena/v1/*` only,
 * adds no credentials and passes the caller's address on for the arena's hashed rate limits. */
const ARENA = process.env.ARENA_API_URL ?? "http://localhost:8100";

function envelope(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, detail: null } }, { status });
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((seg) => seg === "." || seg === ".." || /[\\/]/.test(seg))) return envelope(404, "not_found", "Unknown path.");
  if (path[0] !== "arena" || path[1] !== "v1") return envelope(404, "not_found", "Unknown path.");
  const headers: Record<string, string> = {};
  const ct = req.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;
  const fwd = req.headers.get("x-forwarded-for");
  if (fwd) headers["X-Forwarded-For"] = fwd;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  try {
    const upstream = await fetch(`${ARENA}/${path.join("/")}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body: hasBody ? await req.text() : undefined,
      signal: req.signal,
      cache: "no-store",
    });
    const out = new Headers();
    const type = upstream.headers.get("content-type");
    if (type) out.set("content-type", type);
    const retry = upstream.headers.get("retry-after");
    if (retry) out.set("retry-after", retry);
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return envelope(502, "arena_unreachable", "Could not reach the arena.");
  }
}

export { forward as GET, forward as POST };
export const dynamic = "force-dynamic";
