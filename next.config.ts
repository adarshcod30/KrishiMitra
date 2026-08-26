import type { NextConfig } from "next";

/**
 * Security headers applied to every response.
 *
 * HSTS is only honoured by browsers over HTTPS, so it is inert during local
 * `next dev` on http://localhost and active once the hosting edge terminates
 * TLS (Vercel does this for every deployment and custom domain).
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

/**
 * `output: "standalone"` is a SELF-HOSTING feature: it makes `next build` trace
 * the server's real dependency set into `.next/standalone/` so a container can
 * ship `server.js` plus a pruned node_modules instead of the whole tree.
 * Dockerfile.web depends on it and asserts the directory exists, and
 * docker-compose still builds that image, so it must stay on by default.
 *
 * Vercel does NOT want it. Its Next.js build adapter produces Build Output API
 * v3 (`.vercel/output/functions/**`) directly and does its own tracing; the
 * standalone bundle is at best dead weight copied into every build, and at
 * worst it diverges from what the adapter traced. Vercel's own self-hosting
 * docs are explicit that `standalone` is for running Next.js yourself.
 *
 * So: emit standalone everywhere EXCEPT on Vercel, which sets `VERCEL=1` in
 * every build environment. `DOCKER_BUILD=1` forces it back on, which is only
 * needed in the odd case of building the container image from inside a Vercel
 * build environment.
 *
 * Spread rather than `output: undefined` so the key is genuinely absent from
 * the config object on Vercel instead of being present-but-undefined.
 */
const isVercelBuild = process.env.VERCEL === "1";
const forceStandalone = process.env.DOCKER_BUILD === "1";
const standaloneOutput = forceStandalone || !isVercelBuild;

const nextConfig: NextConfig = {
  ...(standaloneOutput ? { output: "standalone" as const } : {}),
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
