import { NextResponse } from "next/server";

const API = process.env.GAUNTLET_API_URL ?? "http://localhost:8000";

function envelope(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, detail: null } }, { status });
}

/** Validate an API key against the API and store it in an httpOnly cookie. */
export async function POST(req: Request) {
  let key = "";
  try {
    const body = (await req.json()) as { api_key?: unknown };
    key = typeof body.api_key === "string" ? body.api_key.trim() : "";
  } catch {
    return envelope(400, "bad_request", "Send a JSON body with an api_key.");
  }
  if (!key) return envelope(400, "bad_request", "Enter an API key.");
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/v1/projects`, { headers: { Authorization: `Bearer ${key}` } });
  } catch {
    return envelope(502, "api_unreachable", "Could not reach the Gauntlet API.");
  }
  if (upstream.status === 401) return envelope(401, "unauthorized", "That API key was not accepted.");
  if (!upstream.ok) return envelope(upstream.status, "error", "The API rejected the request.");
  const res = NextResponse.json({ ok: true });
  res.cookies.set("gauntlet_key", key, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production" && process.env.GAUNTLET_INSECURE_COOKIE !== "1",
    path: "/",
  });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set("gauntlet_key", "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
