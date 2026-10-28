import { describe, expect, it } from "vitest";

import { clientHeaders } from "@/proxy";

describe("clientHeaders (BE-10, M10)", () => {
  const incoming = () =>
    new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.7", "x-real-ip": "6.6.6.6", cookie: "a=b" });

  it("drops every client-sent forwarding header by default", () => {
    const h = clientHeaders(incoming(), false);
    expect(h.get("x-forwarded-for")).toBeNull();
    expect(h.get("x-real-ip")).toBeNull();
    expect(h.get("cookie")).toBe("a=b");
  });

  it("keeps only the edge proxy's last hop behind a trusted edge", () => {
    const h = clientHeaders(incoming(), true);
    expect(h.get("x-forwarded-for")).toBe("203.0.113.7");
    expect(h.get("x-real-ip")).toBeNull();
  });

  it("sends nothing behind a trusted edge when no header arrived", () => {
    expect(clientHeaders(new Headers(), true).get("x-forwarded-for")).toBeNull();
  });
});
