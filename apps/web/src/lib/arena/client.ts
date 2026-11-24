import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, parseErrorBody } from "@/lib/api/errors";

import type { paths } from "./schema";

const errors: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return undefined;
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      body = null;
    }
    throw parseErrorBody(response.status, body);
  },
};

/** The arena service through the web app's public proxy (no sign-in, no credentials). */
export const arena = createClient<paths>({ baseUrl: "/api/arena" });
arena.use(errors);

export function arenaBody<T>(res: { data?: T }): T {
  if (res.data === undefined) throw new ApiError(500, "empty", "The arena returned no data.");
  return res.data;
}
