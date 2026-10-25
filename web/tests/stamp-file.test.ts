import { describe, expect, it } from "vitest";

import { stampProblem } from "@/lib/stamp-file";

const MB = 1024 * 1024;

describe("stampProblem (mirrors backend/app/services/stamps.py)", () => {
  it("accepts a PNG of any shape whose longest side is at least 300 px, and any SVG up to 1 MB", () => {
    expect(stampProblem({ kind: "png", size: 200_000, width: 300, height: 300 })).toBeNull();
    expect(stampProblem({ kind: "png", size: 7_000, width: 656, height: 211 })).toBeNull();
    expect(stampProblem({ kind: "png", size: 9_000, width: 211, height: 656 })).toBeNull();
    expect(stampProblem({ kind: "png", size: MB, width: 1200, height: 1200 })).toBeNull();
    expect(stampProblem({ kind: "svg", size: 4_000 })).toBeNull();
  });

  it("rejects files over 1 MB", () => {
    expect(stampProblem({ kind: "svg", size: MB + 1 })).toBe("The file is larger than 1 MB.");
    expect(stampProblem({ kind: "png", size: MB + 1, width: 600, height: 600 })).toBe("The file is larger than 1 MB.");
  });

  it("rejects other file types", () => {
    expect(stampProblem({ kind: "other", size: 10 })).toBe("Upload a PNG or SVG image.");
  });

  it("rejects a PNG whose longest side is under 300 px", () => {
    expect(stampProblem({ kind: "png", size: 10, width: 299, height: 120 })).toBe(
      "The PNG's longest side must be at least 300 px; this one is 299x120.",
    );
  });

  it("rejects a PNG it couldn't read", () => {
    expect(stampProblem({ kind: "png", size: 10 })).toBe("Upload a PNG or SVG image; this PNG can't be read.");
  });
});
