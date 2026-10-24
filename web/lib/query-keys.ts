// FE-02: every TanStack Query key in one place, so mutations invalidate the right lists.
export const queryKeys = {
  session: ["session"] as const,
  verify: {
    code: (code: string) => ["verify", "code", code] as const,
    independent: (input: unknown) => ["verify", "independent", input] as const,
  },
  admin: {
    all: ["admin"] as const,
    dashboard: ["admin", "dashboard"] as const,
    students: (params: Record<string, unknown> = {}) => ["admin", "students", params] as const,
    student: (id: string) => ["admin", "student", id] as const,
    programs: ["admin", "programs"] as const,
    skills: ["admin", "skills"] as const,
    versions: (params: Record<string, unknown> = {}) => ["admin", "versions", params] as const,
  },
};
