import { NextResponse, type NextRequest } from "next/server";

/** Pass the request path to server layouts so the auth redirect can carry `next`. */
export function proxy(req: NextRequest) {
  const headers = new Headers(req.headers);
  headers.set("x-pathname", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: ["/((?!_next|api|favicon.ico).*)"] };
