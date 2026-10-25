// Verification codes and verdict wording, shared by the verify pages (FE-10, FE-11).
// normalizeCode mirrors backend/app/services/codes.py.
import type { components } from "@/lib/api-types";

export type Verdict = components["schemas"]["VerifyResult"]["verdict"];

// Crockford base32: no I, L, O, U.
const ALPHABET = /^[0-9A-HJKMNP-TV-Z]+$/;
const LOOK_ALIKES: Record<string, string> = { O: "0", I: "1", L: "1" };

/** 'K7QM3XWP9D' -> 'K7QM-3XWP-9D' (how it is printed and shown). */
export function formatCode(code: string): string {
  return `${code.slice(0, 4)}-${code.slice(4, 8)}-${code.slice(8)}`;
}

/** Any case, dashes and spaces, and the look-alikes O, I, L; null for anything else. */
export function normalizeCode(text: string): string | null {
  const code = text
    .replace(/[\s-]/g, "")
    .toUpperCase()
    .replace(/[OIL]/g, (c) => LOOK_ALIKES[c]);
  return ALPHABET.test(code) ? code : null;
}

export function verdictHeadline(verdict: Verdict, latestVersionNo?: number | null): string {
  switch (verdict) {
    case "VALID":
      return "Valid — issued by BTU";
    case "SUPERSEDED":
      return `Authentic, but superseded by version ${latestVersionNo ?? "?"} — ask the holder for the current one`;
    case "NOT_FOUND":
      return "Not valid — this file doesn't match any passport BTU issued";
    case "UNKNOWN_CODE":
      return "Unknown code — check it and try again";
    case "NOT_ISSUED_BY_BTU":
      return "Not issued by BTU";
    case "REVOKED":
      return "Revoked by BTU";
  }
}

/** '2026-10-22T15:41:00Z' or '2026-10-22' -> '22 October 2026'. */
export function formatDate(value: string): string {
  return new Date(value.length === 10 ? `${value}T00:00:00Z` : value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** An instant in the viewer's local time, e.g. '25 Oct 2026, 14:05' (admin tables). */
export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Today's date as YYYY-MM-DD in BTU's timezone (the API's TIMEZONE default), for date checks. */
export function todayInTbilisi(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tbilisi" }).format(now);
}

/** '2026-10-25T17:30:00Z' -> '21:30' in the viewer's local time (event times on screens). */
export function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** A title for display type: every word but the last heavy, the last one light. */
export function splitTitle(title: string): [string, string | undefined] {
  const words = title.trim().split(/\s+/);
  return words.length < 2 ? [title, undefined] : [words.slice(0, -1).join(" "), words.at(-1)];
}
