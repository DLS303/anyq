import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  compress: true,
  poweredByHeader: false,
  outputFileTracingRoot: path.join(__dirname),
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "three",
      "pdfjs-dist",
      "xlsx",
      "jspdf",
      "jspdf-autotable",
      "@turf/turf",
      "leaflet",
    ],
  },
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8010";
    return [{ source: "/uploads/:path*", destination: `${backendUrl}/uploads/:path*` }];
  },
};

export default nextConfig;
