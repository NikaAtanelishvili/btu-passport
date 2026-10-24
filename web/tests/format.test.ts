// Code formatting and normalising (same cases as backend/tests/unit/test_codes.py) and the
// verdict headlines of FE-11.
import { describe, expect, it } from "vitest";

import { formatCode, normalizeCode, todayInTbilisi, verdictHeadline } from "@/lib/format";

describe("codes", () => {
  it("formats as XXXX-XXXX-XX", () => {
    expect(formatCode("K7QM3XWP9D")).toBe("K7QM-3XWP-9D");
  });

  it.each([
    ["K7QM3XWP9D", "K7QM3XWP9D"],
    ["k7qm-3xwp-9d", "K7QM3XWP9D"],
    [" K7QM 3XWP 9D ", "K7QM3XWP9D"],
    ["O0IL", "0011"],
    ["o-i-l", "011"],
  ])("normalizes %j", (text, expected) => {
    expect(normalizeCode(text)).toBe(expected);
  });

  it.each(["K7QM3XWP9U", "K7QM_3XWP", "K7QM3XWP9!", "ÄBC", "", " - "])(
    "rejects %j",
    (text) => {
      expect(normalizeCode(text)).toBeNull();
    },
  );
});

describe("verdictHeadline", () => {
  it.each([
    ["VALID", "Valid — issued by BTU"],
    ["NOT_FOUND", "Not valid — this file doesn't match any passport BTU issued"],
    ["UNKNOWN_CODE", "Unknown code — check it and try again"],
    ["NOT_ISSUED_BY_BTU", "Not issued by BTU"],
    ["REVOKED", "Revoked by BTU"],
  ] as const)("%s", (verdict, headline) => {
    expect(verdictHeadline(verdict)).toBe(headline);
  });

  it("names the latest version for SUPERSEDED", () => {
    expect(verdictHeadline("SUPERSEDED", 3)).toBe(
      "Authentic, but superseded by version 3 — ask the holder for the current one",
    );
  });
});

describe("todayInTbilisi", () => {
  it("uses Tbilisi's date (UTC+4), not the browser's or UTC", () => {
    expect(todayInTbilisi(new Date("2026-10-25T19:59:00Z"))).toBe("2026-10-25");
    expect(todayInTbilisi(new Date("2026-10-25T20:00:00Z"))).toBe("2026-10-26");
  });
});
