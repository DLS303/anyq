import path from "node:path";
import type { NextConfig } from "next";

// Leaflet tiles, the ArcGIS imagery layer, and a same-origin pdf.js worker.
// Next hydration and that worker need inline/eval scripts; frame-ancestors blocks embedding.
const WEB_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://server.arcgisonline.com",
  "connect-src 'self' https://*.tile.openstreetmap.org https://server.arcgisonline.com https://unpkg.com",
  "worker-src 'self' blob:",
  "font-src 'self' data:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=86400" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: WEB_CSP },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  compress: true,
  poweredByHeader: false,
  images: {
    formats: ["image/avif", "image/webp"],
    deviceSizes: [360, 414, 640, 768, 828, 1080, 1200],
    imageSizes: [64, 96, 128, 256, 384],
    minimumCacheTTL: 60 * 60 * 24 * 30,
  },
  output: "standalone",
  // Workspace packages are installed at the repository root. Standalone
  // tracing has to start there so the production image contains them.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  async headers() {
    return [
      { source: "/:path*", headers: SECURITY_HEADERS },
      {
        source: "/:locale/r/daily/:token",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
    ];
  },
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "three",
      "pdfjs-dist",
      "xlsx",
      "jspdf",
      "@turf/turf",
      "leaflet",
    ],
  },
  async rewrites() {
    const backendUrl = process.env.INTERNAL_API_URL || "http://127.0.0.1:8010";
    return [
      { source: "/v1/:path*", destination: `${backendUrl}/v1/:path*` },
      { source: "/health", destination: `${backendUrl}/health` },
      { source: "/uploads/:path*", destination: `${backendUrl}/uploads/:path*` },
    ];
  },
};

export default nextConfig;
