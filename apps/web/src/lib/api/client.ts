import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, parseErrorBody } from "./errors";
import type { paths } from "./schema";

const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return undefined;
    if (response.status === 401 && typeof window !== "undefined") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload clears the query cache
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      body = null;
    }
    throw parseErrorBody(response.status, body);
  },
};

export const client = createClient<paths>({ baseUrl: "/api/gauntlet" });
client.use(errorMiddleware);

/** Take the body out of an openapi-fetch result (errors already threw in the middleware). */
export function bodyOf<T>(res: { data?: T }): T {
  if (res.data === undefined) throw new ApiError(500, "empty", "The API returned no data.");
  return res.data;
}

export { ApiError };
