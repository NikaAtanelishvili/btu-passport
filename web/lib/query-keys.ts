// FE-02: every TanStack Query key in one place, so mutations invalidate the right lists.
export const queryKeys = {
  session: ["session"] as const,
  verify: {
    code: (code: string) => ["verify", "code", code] as const,
    independent: (input: unknown) => ["verify", "independent", input] as const,
  },
  admin: {
    students: (params: Record<string, unknown> = {}) => ["admin", "students", params] as const,
  },
};
