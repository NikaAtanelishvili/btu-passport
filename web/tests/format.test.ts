// Code formatting and normalising (same cases as backend/tests/unit/test_codes.py) and the
// verdict headlines of FE-11.
import { describe, expect, it } from "vitest";

import { formatCode, normalizeCode, splitTitle, todayInTbilisi, verdictHeadline } from "@/lib/format";
import { fromLocalInput, shiftLocal, toLocalInput } from "@/lib/events";

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

describe("event datetime-local helpers", () => {
  it("round-trips a local input through UTC", () => {
    const local = "2026-10-21T14:30";
    expect(toLocalInput(fromLocalInput(local))).toBe(local);
  });

  it("shifts by minutes", () => {
    expect(shiftLocal("2026-10-21T14:30", -15)).toBe("2026-10-21T14:15");
    expect(shiftLocal("2026-10-21T23:45", 30)).toBe("2026-10-22T00:15");
  });
});

describe("splitTitle", () => {
  it("makes the last word the light part", () => {
    expect(splitTitle("Prompt Engineering Workshop")).toEqual(["Prompt Engineering", "Workshop"]);
    expect(splitTitle("  Hackathon ")).toEqual(["  Hackathon ", undefined]);
  });
});
