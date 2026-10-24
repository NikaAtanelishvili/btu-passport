"use client";

// FE-03: who is signed in. The server enforces every rule; this only picks the right screen.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { queryKeys } from "@/lib/query-keys";

export type SessionInfo = components["schemas"]["SessionInfo"];
export type RequiredRole = "student" | "admin" | "super_admin";

export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: async (): Promise<SessionInfo> => {
      const { data } = await api.GET("/api/session");
      return data ?? { authenticated: false };
    },
    staleTime: 30_000,
  });
}

export function hasRole(session: SessionInfo, role: RequiredRole): boolean {
  if (!session.authenticated) return false;
  if (role === "student") return session.student != null;
  if (role === "admin") return session.role === "ADMIN" || session.role === "SUPER_ADMIN";
  return session.role === "SUPER_ADMIN";
}

/** Where a signed-in user belongs: same rule as the API's post-sign-in redirect. */
export function homeFor(session: SessionInfo): string {
  if (hasRole(session, "admin")) return "/admin";
  if (hasRole(session, "student")) return "/me";
  return "/";
}

export async function signOut(): Promise<void> {
  await api.POST("/auth/logout");
  // Full load so every cached query starts fresh.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign("/");
}
