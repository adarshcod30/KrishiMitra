import type { NextConfig } from "next";

/**
 * Security headers applied to every response.
 *
 * HSTS is only honoured by browsers over HTTPS, so it is inert during local
 * `next dev` on http://localhost and active once Cloud Run terminates TLS.
 */
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-DNS-Prefetch-Control", value: "on" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains"
  }
];

const nextConfig: NextConfig = {
  // Cloud Run images copy .next/standalone instead of the whole node_modules
  // tree, which keeps the runtime image small.
  output: "standalone",
  typedRoutes: true,
  poweredByHeader: false,
  // next@16.3 writes AGENTS.md + CLAUDE.md into the repo root on every
  // `next dev`. A generated repo-root CLAUDE.md would silently become this
  // project's agent instructions, so the generator stays off.
  agentRules: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS
      }
    ];
  }
};

export default nextConfig;
