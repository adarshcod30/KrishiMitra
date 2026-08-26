/**
 * Error helpers shared by the API client and the UI.
 *
 * The point of this module is that a raw FastAPI error body
 * (`{"detail":[{"type":"string_too_short","loc":["query","q"], ...}]}`) must
 * never reach a farmer's screen. `ApiError` carries an already-flattened,
 * human-readable `detail`, and `toUserMessage()` turns anything thrown by
 * `fetch` into one sentence that can be rendered as-is.
 */

/** Status used when the request never reached the server at all. */
export const NETWORK_ERROR_STATUS = 0;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  get isNetworkError(): boolean {
    return this.status === NETWORK_ERROR_STATUS;
  }
}

/** Raised for input the API is known to reject, so we never send the request. */
export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

function truncate(value: string, max = 240): string {
  const trimmed = value.trim();
  return trimmed.length > max ? `${trimmed.slice(0, max - 1)}…` : trimmed;
}

interface FastApiValidationItem {
  msg?: unknown;
  loc?: unknown;
}

function describeValidationItem(item: FastApiValidationItem): string {
  const message = typeof item.msg === "string" ? item.msg : "Invalid value";
  const field = Array.isArray(item.loc)
    ? item.loc.filter((part) => typeof part === "string" && part !== "query" && part !== "body").pop()
    : undefined;
  return typeof field === "string" ? `${field}: ${message}` : message;
}

/** Flattens a FastAPI/JSON error payload into a single readable sentence. */
export function flattenErrorPayload(payload: unknown): string | null {
  if (typeof payload === "string") {
    return payload.trim() ? truncate(payload) : null;
  }
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const detail = (payload as { detail?: unknown; message?: unknown }).detail
    ?? (payload as { message?: unknown }).message;

  if (typeof detail === "string") {
    return detail.trim() ? truncate(detail) : null;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => describeValidationItem((item ?? {}) as FastApiValidationItem))
      .filter(Boolean);
    return parts.length ? truncate(parts.join("; ")) : null;
  }
  return null;
}

/** Builds an `ApiError` from a non-2xx `Response`, reading the body safely. */
export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const raw = await response.text();
    if (raw.trim()) {
      try {
        detail = flattenErrorPayload(JSON.parse(raw) as unknown);
      } catch {
        // Not JSON (an HTML error page, a proxy message, ...).
        detail = truncate(raw);
      }
    }
  } catch {
    detail = null;
  }

  return new ApiError(
    response.status,
    detail ?? `Request failed (${response.status} ${response.statusText || "error"}).`
  );
}

const NETWORK_MESSAGE =
  "Cannot reach the AgroTech service. Check your connection and that the ML API is running.";

/**
 * Converts anything thrown by the API client into a message safe to render.
 * `fallback` is used only when nothing more specific can be determined.
 */
export function toUserMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof ValidationError) {
    return error.message;
  }

  if (error instanceof ApiError) {
    if (error.isNetworkError) {
      return NETWORK_MESSAGE;
    }
    if (error.status >= 500) {
      return `The AgroTech service reported an error (${error.status}). Please try again in a moment.`;
    }
    if (error.status === 404) {
      return "No matching record was found.";
    }
    return error.detail;
  }

  // `fetch` rejects with a TypeError when the request never left the browser.
  if (error instanceof TypeError) {
    return NETWORK_MESSAGE;
  }

  if (error instanceof Error && error.message.trim()) {
    return truncate(error.message);
  }

  return fallback;
}
