import type { NextConfig } from "next";

// The browser only ever talks to this origin; FastAPI sits behind these rewrites.
const api = process.env.API_ORIGIN ?? "http://localhost:8000";

// BTU's issuer identity, built into the page for the independent check (FE-12) to fall back
// on when the issuer file can't be fetched because the API is down. `make web` exports .env.
const btuIssuer = {
  issuer_name: "Business and Technology University",
  chain_id: Number(process.env.CHAIN_ID ?? 0),
  contract_address: process.env.CONTRACT_ADDRESS ?? "",
  issuer_address: process.env.ISSUER_ADDRESS ?? "",
};

// Phone test over the LAN (README "Phone test over the LAN"): PUBLIC_BASE_URL is the laptop's
// LAN address, and the dev server must serve its assets (HMR, chunks) to pages opened there;
// Next.js blocks cross-origin dev resources unless the host is listed. Dev only.
const publicHost = new URL(process.env.PUBLIC_BASE_URL ?? "http://localhost:3000").hostname;

const nextConfig: NextConfig = {
  allowedDevOrigins: [publicHost],
  env: { NEXT_PUBLIC_BTU_ISSUER: JSON.stringify(btuIssuer) },
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Every page is a client component that fetches its own data (Frontend tab §2), so no
    // page can render instantly from the prefetch; validate only segments that opt in with
    // `export const instant`. Stops "Could not validate … instant navigation" on each load.
    instantInsights: { validationLevel: "manual-warning" },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // FE-10: `/` is an alias of the public Verify page, kept for old links and the bare domain.
  async redirects() {
    return [{ source: "/", destination: "/verify", permanent: false }];
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
