// Program combobox: which programs match the search and when to offer a new one.
import { describe, expect, it } from "vitest";

import { matchPrograms } from "@/components/program-field";

const programs = ["Information Technologies", "Business Administration", "Computer Science"];

describe("matchPrograms", () => {
  it("lists every program before anything is typed, and offers nothing new", () => {
    expect(matchPrograms(programs, "  ")).toEqual({ matches: programs, offerNew: false });
  });

  it("filters case-insensitively by substring", () => {
    expect(matchPrograms(programs, "SCI").matches).toEqual(["Computer Science"]);
  });

  it("offers the typed text when nothing matches exactly", () => {
    expect(matchPrograms(programs, "Data")).toEqual({ matches: [], offerNew: true });
    expect(matchPrograms(programs, "Computer").offerNew).toBe(true);
  });

  it("puts an exact match first, so Enter picks what was typed", () => {
    const list = ["Data-Driven Digital Marketing", "Digital Marketing"];
    expect(matchPrograms(list, "digital marketing").matches).toEqual(["Digital Marketing", "Data-Driven Digital Marketing"]);
  });

  it("offers nothing new on an exact match, ignoring case and spaces", () => {
    expect(matchPrograms(programs, " computer science ").offerNew).toBe(false);
  });
});
