// BC-05 / BC-06: the browser library against shared/merkle-vectors.json.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  hashPair,
  leafFromPdfSha256,
  processProof,
  sha256File,
} from "@/lib/merkle";

type VectorCase = {
  name: string;
  pdf_sha256: string[];
  leaves: string[];
  root: string;
  proofs: Record<string, string[]>;
};

const vectors = JSON.parse(
  readFileSync(new URL("../../shared/merkle-vectors.json", import.meta.url), "utf8"),
) as { cases: VectorCase[] };

describe("shared Merkle vectors", () => {
  it("has the six cases", () => {
    expect(vectors.cases.map((c) => c.pdf_sha256.length)).toEqual([1, 2, 3, 4, 5, 7]);
  });

  for (const c of vectors.cases) {
    it(`${c.name}: leaves match`, () => {
      expect(c.pdf_sha256.map(leafFromPdfSha256)).toEqual(c.leaves);
    });

    it(`${c.name}: every proof leads to the root`, () => {
      for (const [pdf, proof] of Object.entries(c.proofs)) {
        expect(processProof(leafFromPdfSha256(pdf), proof)).toBe(c.root);
      }
    });
  }

  it("a flipped byte in the PDF hash misses the root", () => {
    const c = vectors.cases[3];
    const pdf = c.pdf_sha256[0];
    const flipped = pdf.slice(0, -1) + (pdf.endsWith("0") ? "1" : "0");
    expect(processProof(leafFromPdfSha256(flipped), c.proofs[pdf])).not.toBe(c.root);
  });
});

describe("helpers", () => {
  it("hashPair is order-independent", () => {
    const [a, b] = vectors.cases[1].leaves;
    expect(hashPair(a, b)).toBe(hashPair(b, a));
  });

  it("accepts uppercase and unprefixed hex", () => {
    const pdf = vectors.cases[0].pdf_sha256[0];
    expect(leafFromPdfSha256(pdf.slice(2).toUpperCase())).toBe(leafFromPdfSha256(pdf));
  });

  it("rejects malformed hashes", () => {
    expect(() => leafFromPdfSha256("0x1234")).toThrow();
    expect(() => leafFromPdfSha256("0x" + "g".repeat(64))).toThrow();
  });

  it("sha256File hashes the file bytes locally", async () => {
    const bytes = new TextEncoder().encode("%PDF-1.7 test");
    const expected = "0x" + createHash("sha256").update(bytes).digest("hex");
    expect(await sha256File(new File([bytes], "p.pdf"))).toBe(expected);
  });
});
