import type { NextConfig } from "next";

const commonSecurityHeaders = [
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value:
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
  },
  {
    key: "Cross-Origin-Opener-Policy",
    value: "same-origin",
  },
  {
    key: "Cross-Origin-Resource-Policy",
    value: "same-origin",
  },
];

const competitionCsp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "connect-src 'self'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: commonSecurityHeaders,
      },
      {
        source: "/tbb-sme-2026/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: competitionCsp,
          },
        ],
      },
      {
        source: "/api/sme-liquidity/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "default-src 'none'; frame-ancestors 'none'",
          },
          {
            key: "X-Robots-Tag",
            value: "noindex, nofollow, nosnippet",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
