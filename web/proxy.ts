// Strips client-supplied forwarding headers before /api and /auth are proxied to FastAPI.
// The Next.js rewrite passes them through untouched, so the API would otherwise trust a
// spoofed client IP for its per-IP rate limits (BE-10). In dev every request then counts
// as 127.0.0.1; behind Caddy (demo) /api and /auth bypass Next.js and Caddy sets the header.
//
// TRUSTED_EDGE_PROXY=true (Railway, M10): this app sits behind the host's edge proxy, which
// appends the real client address as the last X-Forwarded-For hop. That hop alone is passed
// on; anything earlier was written by the client and is dropped.
import { NextResponse, type NextRequest } from "next/server";

export function clientHeaders(incoming: Headers, trustedEdge: boolean): Headers {
  const headers = new Headers(incoming);
  const forwarded = incoming.get("x-forwarded-for");
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  if (trustedEdge && forwarded) {
    const last = forwarded.split(",").at(-1)?.trim();
    if (last) headers.set("x-forwarded-for", last);
  }
  return headers;
}

export function proxy(request: NextRequest) {
  const headers = clientHeaders(request.headers, process.env.TRUSTED_EDGE_PROXY === "true");
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: ["/api/:path*", "/auth/:path*"] };
