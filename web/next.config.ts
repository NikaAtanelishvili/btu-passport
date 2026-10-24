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

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_BTU_ISSUER: JSON.stringify(btuIssuer) },
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
