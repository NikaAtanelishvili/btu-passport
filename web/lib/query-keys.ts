// FE-02: every TanStack Query key in one place, so mutations invalidate the right lists.
export const queryKeys = {
  session: ["session"] as const,
  authProviders: ["auth", "providers"] as const,
  verify: {
    code: (code: string) => ["verify", "code", code] as const,
    independent: (input: unknown) => ["verify", "independent", input] as const,
  },
  checkin: (eventId: string, t: string) => ["checkin", eventId, t] as const,
  checkinPass: (eventId: string, t: string) => ["checkin-pass", eventId, t] as const,
  me: {
    passport: ["me", "passport"] as const,
    versions: ["me", "versions"] as const,
    events: ["me", "events"] as const,
  },
  admin: {
    all: ["admin"] as const,
    dashboard: ["admin", "dashboard"] as const,
    students: (params: Record<string, unknown> = {}) => ["admin", "students", params] as const,
    student: (id: string) => ["admin", "student", id] as const,
    programs: ["admin", "programs"] as const,
    skills: ["admin", "skills"] as const,
    skillsAll: ["admin", "skills", "all"] as const,
    categories: (includeArchived: boolean) => ["admin", "categories", includeArchived] as const,
    roles: ["admin", "roles"] as const,
    audit: (params: Record<string, unknown> = {}) => ["admin", "audit", params] as const,
    auditActions: ["admin", "audit", "actions"] as const,
    versions: (params: Record<string, unknown> = {}) => ["admin", "versions", params] as const,
    events: (params: Record<string, unknown> = {}) => ["admin", "events", params] as const,
    event: (id: string) => ["admin", "event", id] as const,
    participants: (id: string) => ["admin", "participants", id] as const,
    qr: (id: string) => ["admin", "qr", id] as const,
  },
};
