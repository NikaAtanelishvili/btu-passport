// FE-02: the one typed API client. Same origin (Next.js rewrites /api and /auth to FastAPI),
// CSRF header on unsafe methods, and every non-2xx response becomes an ApiError.
import createClient, { type ClientOptions, type Middleware } from "openapi-fetch";

import type { paths } from "@/lib/api-types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly error: string,
    message: string,
    readonly fields: Record<string, string> = {},
    /** The whole error body, for extra keys such as `attempts_left`. */
    readonly body: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const GUARDED_PREFIXES = ["/me", "/admin", "/checkin"];

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    body = (await response.clone().json()) as Record<string, unknown>;
  } catch {
    // not JSON (e.g. a proxy error page)
  }
  return new ApiError(
    response.status,
    typeof body.error === "string" ? body.error : "error",
    typeof body.message === "string" ? body.message : `Request failed (${response.status})`,
    (body.fields as Record<string, string> | undefined) ?? {},
    body,
  );
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method)) {
      const token = readCookie("csrf_token");
      if (token) request.headers.set("X-CSRF-Token", token);
    }
    return request;
  },
};

export const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return response;
    const error = await toApiError(response);
    if (error.status === 401 && typeof window !== "undefined") {
      const { pathname, search } = window.location;
      if (GUARDED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
        // Outside React, so no router here; a full load also resets cached queries.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`);
      }
    }
    throw error;
  },
};

export function createApiClient(options: ClientOptions = {}) {
  const client = createClient<paths>({ baseUrl: "", credentials: "include", ...options });
  client.use(csrfMiddleware, errorMiddleware);
  return client;
}

export const api = createApiClient();
