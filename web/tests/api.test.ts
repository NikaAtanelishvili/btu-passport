// FE-02: API client middleware and server-error mapping.
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
import { toast } from "sonner";

import { ApiError, createApiClient } from "@/lib/api";
import { applyServerErrors } from "@/lib/forms";

function clientWith(respond: (request: Request) => Response) {
  const seen: Request[] = [];
  const client = createApiClient({
    baseUrl: "http://app.test",
    fetch: async (input: Request) => {
      seen.push(input);
      return respond(input);
    },
  });
  return { client, seen };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toast.error).mockClear();
});

describe("csrf middleware", () => {
  it("adds X-CSRF-Token from the cookie on POST, not on GET", async () => {
    vi.stubGlobal("document", { cookie: "session=s; csrf_token=tok%3D1" });
    const { client, seen } = clientWith(() => new Response(null, { status: 204 }));
    await client.POST("/auth/logout");
    await client.GET("/api/session");
    expect(seen[0].headers.get("X-CSRF-Token")).toBe("tok=1");
    expect(seen[1].headers.get("X-CSRF-Token")).toBeNull();
  });
});

describe("error middleware", () => {
  it("throws ApiError with fields and extra body keys", async () => {
    const body = {
      error: "code_invalid",
      message: "Wrong code, 4 tries left.",
      fields: { code: "Wrong code" },
      attempts_left: 4,
    };
    const { client } = clientWith(() => Response.json(body, { status: 400 }));
    const error = await client
      .POST("/auth/verify-code", { body: { email: "a@btu.test", code: "123456" } })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect([apiError.status, apiError.error, apiError.fields]).toEqual([
      400,
      "code_invalid",
      { code: "Wrong code" },
    ]);
    expect(apiError.body.attempts_left).toBe(4);
  });
});

describe("applyServerErrors", () => {
  it("puts field errors under their fields", () => {
    const setError = vi.fn();
    applyServerErrors({ setError }, new ApiError(422, "x", "m", { email: "Use your BTU email" }));
    expect(setError).toHaveBeenCalledWith("email", { type: "server", message: "Use your BTU email" });
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts the message when there are no field errors", () => {
    const setError = vi.fn();
    applyServerErrors({ setError }, new ApiError(429, "rate_limited", "Too many codes"));
    expect(setError).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Too many codes");
  });
});
