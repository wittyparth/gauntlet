import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

const API = process.env.GAUNTLET_API_URL ?? "http://localhost:8000";

function envelope(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, detail: null } }, { status });
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path[0] !== "v1") return envelope(404, "not_found", "Unknown path.");
  // The public benchmarks page reads this one route without signing in.
  const isPublic = req.method === "GET" && path.join("/") === "v1/meta/benchmarks";
  const key = (await cookies()).get("gauntlet_key")?.value;
  if (!key && !isPublic) return envelope(401, "unauthorized", "Sign in to continue.");

  const url = `${API}/${path.join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = key ? { Authorization: `Bearer ${key}` } : {};
  const accept = req.headers.get("accept");
  if (accept) headers.Accept = accept;
  const ct = req.headers.get("content-type");
  if (ct) headers["Content-Type"] = ct;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body: hasBody ? await req.text() : undefined,
      signal: req.signal,
      cache: "no-store",
    });
  } catch {
    return envelope(502, "api_unreachable", "Could not reach the Gauntlet API.");
  }
  const out = new Headers();
  const type = upstream.headers.get("content-type");
  if (type) out.set("content-type", type);
  if (type?.includes("text/event-stream")) {
    out.set("cache-control", "no-cache, no-transform");
    out.set("x-accel-buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE, forward as PATCH };
export const dynamic = "force-dynamic";
