import { NextResponse, type NextRequest } from "next/server";

/**
 * Same-origin proxy to the FastAPI ML service.
 *
 * Why this exists: `NEXT_PUBLIC_ML_API_URL` is inlined into the client bundle at
 * BUILD time. Baking an absolute URL in means the deployed revision can never be
 * repointed without a rebuild, and baking in a localhost fallback means every
 * visitor's browser calls their OWN machine. Routing through this handler lets
 * the browser use a relative path while the server reads `ML_API_URL` — an
 * ordinary, non-public env var that Vercel can change from the dashboard and
 * apply by redeploying the existing build, with no source rebuild.
 *
 * Requests and responses are streamed, so multipart uploads keep their original
 * boundaries and large payloads are never buffered in memory.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Vercel function wall-clock budget, in seconds.
 *
 * 60 is the ceiling on the Hobby plan for a classic serverless invocation, and
 * is accepted on every plan and in every compute mode, so it is the value that
 * cannot fail a deploy. It must stay comfortably ABOVE
 * `UPSTREAM_TIMEOUT_MS` — otherwise the platform kills the invocation first and
 * the caller gets Vercel's opaque FUNCTION_INVOCATION_TIMEOUT page instead of
 * the JSON error this handler is careful to produce.
 *
 * Next.js requires this to be a statically analysable literal, so it cannot be
 * derived from the constant below.
 */
export const maxDuration = 60;

/**
 * How long to wait for the upstream to send RESPONSE HEADERS.
 *
 * A Hugging Face Space that has scaled to zero takes roughly 30 seconds — and
 * occasionally longer — to wake, and it holds the connection open while it
 * does. That is a legitimate slow response, not a failure, so the budget has to
 * cover it. 50s leaves ~10s of headroom under `maxDuration` for us to serialise
 * a real error.
 *
 * The timer is cleared the moment headers arrive: body streaming is then only
 * bounded by `maxDuration`, so a slow large download is not cut off mid-flight.
 */
const UPSTREAM_TIMEOUT_MS = 50_000;

/** Seconds advertised in `Retry-After` when the backend looks like it is waking. */
const RETRY_AFTER_SECONDS = 15;

/** Local dev default. Server-side only — never reaches the browser bundle. */
const DEV_ML_API_URL = "http://127.0.0.1:8000";

// Default backend for deployed builds when ML_API_URL is not set. This is the
// project's public Render service — not a secret — and the env var always wins,
// so a fork or a re-deploy can repoint without touching source. Local dev is
// unaffected: outside production the fallback stays 127.0.0.1.
const DEPLOYED_ML_API_URL = "https://krishimitra-api-t0wu.onrender.com";

/** Headers that describe THIS hop and must not be forwarded to the upstream. */
const REQUEST_HEADER_DENYLIST = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-length",
  // Hop-by-hop, and undici refuses outright (UND_ERR_NOT_SUPPORTED) if it is
  // present on a fetch it is asked to make. curl adds `Expect: 100-continue`
  // automatically for bodies over ~1 MB, so forwarding it turned every large
  // file upload into a 502. Browsers never send it; command-line clients do.
  "expect",
  // undici decodes for us; asking upstream for a codec we then re-emit as
  // identity would produce an unreadable body.
  "accept-encoding",
  // The ML service is a separate origin with its own auth; do not leak the
  // frontend's cookies to it.
  "cookie"
]);

const RESPONSE_HEADER_DENYLIST = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length"
]);

function upstreamBaseUrl(): string {
  const configured =
    process.env.ML_API_URL?.trim() || process.env.NEXT_PUBLIC_ML_API_URL?.trim();
  const base =
    configured ||
    (process.env.NODE_ENV === "production" ? DEPLOYED_ML_API_URL : DEV_ML_API_URL);
  return base.replace(/\/+$/, "");
}

function buildRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!REQUEST_HEADER_DENYLIST.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  const forwardedHost = request.headers.get("host");
  if (forwardedHost) {
    headers.set("x-forwarded-host", forwardedHost);
  }
  return headers;
}

function buildResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    if (!RESPONSE_HEADER_DENYLIST.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  return headers;
}

/**
 * Error body shape matches FastAPI's (`{"detail": "..."}`) so `lib/errors.ts`
 * flattens proxy failures through exactly the same path as upstream failures.
 */
function proxyError(status: number, detail: string, retryAfter?: number): NextResponse {
  const headers: Record<string, string> = { "cache-control": "no-store" };
  if (retryAfter !== undefined) {
    headers["retry-after"] = String(retryAfter);
  }
  return NextResponse.json({ detail }, { status, headers });
}

/**
 * undici hides the useful part of a network failure in `cause` — the bare
 * message is always "fetch failed". Surface the syscall code (ECONNREFUSED,
 * ENOTFOUND, ECONNRESET, ...) so an operator can tell "wrong URL" from
 * "backend down" without reading the platform logs.
 */
function describeFetchFailure(caught: unknown): string {
  if (!(caught instanceof Error)) {
    return "unknown error";
  }
  const cause = (caught as { cause?: unknown }).cause;
  const code =
    cause && typeof cause === "object" && typeof (cause as { code?: unknown }).code === "string"
      ? (cause as { code: string }).code
      : undefined;
  const causeMessage =
    cause instanceof Error && cause.message && cause.message !== caught.message
      ? cause.message
      : undefined;

  return code ?? causeMessage ?? caught.message ?? "unknown error";
}

function isTimeout(caught: unknown): boolean {
  return (
    caught instanceof Error &&
    (caught.name === "TimeoutError" || caught.name === "AbortError")
  );
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
): Promise<Response> {
  const base = upstreamBaseUrl();

  // A malformed ML_API_URL (missing scheme, stray quotes from a copied dashboard
  // value) otherwise surfaces as a generic "fetch failed" that reads like the
  // backend is down. Name the actual problem instead.
  if (!/^https?:\/\//i.test(base)) {
    return proxyError(
      500,
      `ML_API_URL is misconfigured: expected an absolute http(s) URL, got "${base}". ` +
        "Set it to the API origin, e.g. https://<user>-<space>.hf.space"
    );
  }

  const { path } = await context.params;
  const suffix = (path ?? []).map(encodeURIComponent).join("/");
  const search = request.nextUrl.search;
  const target = `${base}/${suffix}${search}`;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  // One controller drives two independent cancellations: our own header timeout
  // and the browser hanging up. Without the second, a user navigating away
  // leaves the upstream request running for the full budget.
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort(new DOMException("Upstream header timeout", "TimeoutError"));
  }, UPSTREAM_TIMEOUT_MS);
  const abortOnClientDisconnect = () => controller.abort(request.signal.reason);
  request.signal.addEventListener("abort", abortOnClientDisconnect, { once: true });

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: buildRequestHeaders(request),
    redirect: "manual",
    cache: "no-store",
    signal: controller.signal
  };

  if (hasBody) {
    // Stream the original body straight through. This preserves multipart
    // form-data boundaries for file uploads; `duplex: "half"` is required by
    // undici whenever the body is a ReadableStream.
    init.body = request.body;
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (caught) {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", abortOnClientDisconnect);

    // The client gave up first; nothing useful to send it.
    if (request.signal.aborted) {
      return proxyError(499, "Client closed the request before the ML API responded.");
    }

    if (isTimeout(caught)) {
      return proxyError(
        504,
        `The ML API at ${base} did not respond within ${Math.round(UPSTREAM_TIMEOUT_MS / 1000)}s. ` +
          "If it is hosted on a Hugging Face Space that scaled to zero it is probably still " +
          "waking up — retry in a few seconds.",
        RETRY_AFTER_SECONDS
      );
    }

    return proxyError(
      502,
      `Cannot reach the ML API at ${base} (${describeFetchFailure(caught)}). ` +
        "Check that the service is running and that ML_API_URL points at it.",
      RETRY_AFTER_SECONDS
    );
  }

  // Headers are in. Body streaming is bounded by `maxDuration` from here on, but
  // a client disconnect should still tear down the upstream read.
  clearTimeout(timer);

  const headers = buildResponseHeaders(upstream);
  headers.set("cache-control", "no-store");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
