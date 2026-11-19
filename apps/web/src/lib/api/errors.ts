export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

/** Parse the contract envelope `{"error": {code, message, detail}}`; fall back for anything else. */
export function parseErrorBody(status: number, body: unknown): ApiError {
  if (body && typeof body === "object" && "error" in body) {
    const e = (body as { error?: { code?: unknown; message?: unknown; detail?: unknown } }).error;
    if (e && typeof e.message === "string") {
      return new ApiError(
        status,
        typeof e.code === "string" ? e.code : "error",
        e.message,
        e.detail ?? null,
      );
    }
  }
  if (body && typeof body === "object" && "detail" in body) {
    return new ApiError(
      status,
      "validation_error",
      "The request was not valid.",
      (body as { detail: unknown }).detail,
    );
  }
  return new ApiError(status, "error", `Request failed with status ${status}.`);
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError(0, "network", e instanceof Error ? e.message : "Network error.");
}
