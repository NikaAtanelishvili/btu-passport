// FE-02: every TanStack Query key in one place, so mutations invalidate the right lists.
export const queryKeys = {
  session: ["session"] as const,
  verify: {
    code: (code: string) => ["verify", "code", code] as const,
    independent: (input: unknown) => ["verify", "independent", input] as const,
  },
  checkin: (eventId: string, t: string) => ["checkin", eventId, t] as const,
  me: { events: ["me", "events"] as const },
  admin: {
    all: ["admin"] as const,
    dashboard: ["admin", "dashboard"] as const,
    students: (params: Record<string, unknown> = {}) => ["admin", "students", params] as const,
    student: (id: string) => ["admin", "student", id] as const,
    programs: ["admin", "programs"] as const,
    skills: ["admin", "skills"] as const,
    versions: (params: Record<string, unknown> = {}) => ["admin", "versions", params] as const,
    events: (params: Record<string, unknown> = {}) => ["admin", "events", params] as const,
    event: (id: string) => ["admin", "event", id] as const,
    participants: (id: string) => ["admin", "participants", id] as const,
    qr: (id: string) => ["admin", "qr", id] as const,
  },
};
