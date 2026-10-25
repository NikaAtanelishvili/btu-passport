import { describe, expect, it } from "vitest";

import { stampProblem } from "@/lib/stamp-file";

const MB = 1024 * 1024;

describe("stampProblem (mirrors backend/app/services/stamps.py)", () => {
  it("accepts a square PNG of at least 600 px and any SVG up to 1 MB", () => {
    expect(stampProblem({ kind: "png", size: 200_000, width: 600, height: 600 })).toBeNull();
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

  it("rejects a PNG that isn't square or is smaller than 600 px", () => {
    expect(stampProblem({ kind: "png", size: 10, width: 800, height: 600 })).toBe(
      "The PNG must be square; this one is 800x600.",
    );
    expect(stampProblem({ kind: "png", size: 10, width: 599, height: 599 })).toBe(
      "The PNG must be at least 600x600 px; this one is 599.",
    );
  });

  it("rejects a PNG it couldn't read", () => {
    expect(stampProblem({ kind: "png", size: 10 })).toBe("Upload a PNG or SVG image; this PNG can't be read.");
  });
});
