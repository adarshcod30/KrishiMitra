import { NextResponse, type NextRequest } from "next/server";

/**
 * Same-origin proxy to the FastAPI ML service.
 *
 * Why this exists: `NEXT_PUBLIC_ML_API_URL` is inlined into the client bundle at
 * BUILD time. Baking an absolute URL in means the deployed revision can never be
 * repointed without a rebuild, and baking in a localhost fallback means every
 * visitor's browser calls their OWN machine. Routing through this handler lets
 * the browser use a relative path while the server reads `ML_API_URL` — an
 * ordinary, non-public env var that Cloud Run can change at deploy time.
 *
 * Requests and responses are streamed, so multipart uploads keep their original
 * boundaries and large payloads are never buffered in memory.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Local dev default. Server-side only — never reaches the browser bundle. */
const DEV_ML_API_URL = "http://127.0.0.1:8000";

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
  const base = configured || DEV_ML_API_URL;
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

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> }
): Promise<Response> {
  const { path } = await context.params;
  const suffix = (path ?? []).map(encodeURIComponent).join("/");
  const search = request.nextUrl.search;
  const target = `${upstreamBaseUrl()}/${suffix}${search}`;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: buildRequestHeaders(request),
    redirect: "manual",
    cache: "no-store"
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
    const reason = caught instanceof Error ? caught.message : "unknown error";
    return NextResponse.json(
      { detail: `Cannot reach the ML API at ${upstreamBaseUrl()} (${reason}).` },
      { status: 502, headers: { "cache-control": "no-store" } }
    );
  }

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
