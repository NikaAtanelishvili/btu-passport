// FE-03: role checks used by RequireRole and the header.
import { describe, expect, it } from "vitest";

import { hasRole, homeFor, type SessionInfo } from "@/lib/session";

const user = { email: "x@btu.test", name: "x" };
const sessions: Record<string, SessionInfo> = {
  signedOut: { authenticated: false },
  unregistered: { authenticated: true, user, role: null, student: null },
  student: {
    authenticated: true, user, role: null,
    student: { student_id: "BTU-T-0001", passport_id: "BTU-AI-000125" },
  },
  admin: { authenticated: true, user, role: "ADMIN", student: null },
  superAdmin: { authenticated: true, user, role: "SUPER_ADMIN", student: null },
};

describe("hasRole", () => {
  it.each([
    ["signedOut", false, false, false],
    ["unregistered", false, false, false],
    ["student", true, false, false],
    ["admin", false, true, false],
    ["superAdmin", false, true, true],
  ])("%s: student %s, admin %s, super admin %s", (name, student, admin, superAdmin) => {
    const s = sessions[name];
    expect([hasRole(s, "student"), hasRole(s, "admin"), hasRole(s, "super_admin")]).toEqual([
      student, admin, superAdmin,
    ]);
  });
});

describe("homeFor", () => {
  it("matches the API's redirect rule", () => {
    expect(homeFor(sessions.superAdmin)).toBe("/admin");
    expect(homeFor(sessions.admin)).toBe("/admin");
    expect(homeFor(sessions.student)).toBe("/me");
    expect(homeFor(sessions.unregistered)).toBe("/");
  });
});
