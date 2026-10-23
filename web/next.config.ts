import type { NextConfig } from "next";

// The browser only ever talks to this origin; FastAPI sits behind these rewrites.
const api = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/auth/:path*", destination: `${api}/auth/:path*` },
      { source: "/.well-known/:path*", destination: `${api}/.well-known/:path*` },
    ];
  },
};

export default nextConfig;
