// Strips client-supplied forwarding headers before /api and /auth are proxied to FastAPI.
// The Next.js rewrite passes them through untouched, so the API would otherwise trust a
// spoofed client IP for its per-IP rate limits (BE-10). In dev every request then counts
// as 127.0.0.1; behind Caddy (demo) /api and /auth bypass Next.js and Caddy sets the header.
import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: ["/api/:path*", "/auth/:path*"] };
