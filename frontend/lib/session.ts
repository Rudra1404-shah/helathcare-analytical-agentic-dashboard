/**
 * Session helpers for server components.
 *
 * `requireSession` is what every portal layout calls. Middleware already
 * redirected an unauthenticated visitor, so reaching here without a session
 * means the token expired mid-visit; the redirect handles that case too.
 */

import { redirect } from "next/navigation";

import { apiTry } from "@/lib/api";
import type { Hospital, SessionUser } from "@/lib/types";

export async function currentUser(): Promise<SessionUser | null> {
  const result = await apiTry<SessionUser>("/auth/me");
  return result.ok ? result.data : null;
}

export async function requireSession(): Promise<SessionUser> {
  const user = await currentUser();
  if (!user) redirect("/login");
  return user;
}

/**
 * The hospital an account works at.
 *
 * A ministry account has no hospital of its own, so it is handed the first
 * registered one to inspect. Hospital-scoped accounts can only ever resolve to
 * their own, because the API refuses anything else.
 */
export async function resolveHospital(
  user: SessionUser,
): Promise<{ hospital: Hospital | null; error: string | null }> {
  if (user.hospital_id) {
    const result = await apiTry<Hospital>(`/hospitals/${user.hospital_id}`);
    return result.ok
      ? { hospital: result.data, error: null }
      : { hospital: null, error: result.error };
  }

  const directory = await apiTry<{ items: Hospital[] }>("/hospitals", {
    query: { limit: 1 },
  });
  if (!directory.ok) return { hospital: null, error: directory.error };
  return { hospital: directory.data.items[0] ?? null, error: null };
}
