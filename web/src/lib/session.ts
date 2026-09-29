import "server-only";
import { cookies } from "next/headers";

export const SESSION_COOKIE = "wp_session";
export const ORGANIZATION_COOKIE = "wp_organization";
export const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";
export interface Organization { id: string; name: string; role: string }
export interface WorkspaceSession { userId: string; isDemo: boolean; organizations: Organization[]; organizationId: string | null }

export async function getSessionHeaders(): Promise<Record<string, string>> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  const organization = store.get(ORGANIZATION_COOKIE)?.value;
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(organization ? { "X-Organization-ID": organization } : {}),
  };
}

export async function getWorkspaceSession(): Promise<WorkspaceSession | null> {
  const headers = await getSessionHeaders();
  if (!headers.Authorization) return null;
  try {
    const res = await fetch(`${API_ORIGIN}/api/auth/organizations`, { headers, cache: "no-store" });
    if (!res.ok) return null;
    const { organizations } = await res.json() as { organizations: Organization[] };
    const selected = headers["X-Organization-ID"];
    const identity = await fetch(`${API_ORIGIN}/api/auth/me`, { headers, cache: "no-store" });
    if (!identity.ok) return null;
    const { user_id: userId, is_demo: isDemo } = await identity.json() as { user_id: string; is_demo: boolean };
    if (!userId) return null;
    return { userId, isDemo: isDemo === true, organizations, organizationId: organizations.find((org) => org.id === selected)?.id ?? (!selected && organizations.length === 1 ? organizations[0].id : null) };
  } catch { return null; }
}

/** UI capability checks; the API independently enforces every request. */
export function workspaceRole(session: WorkspaceSession | null): string | null {
  return session?.organizations.find((org) => org.id === session.organizationId)?.role ?? null;
}

export function canManageSettings(session: WorkspaceSession | null): boolean {
  return workspaceRole(session) === "admin" &&
    (session?.organizationId === "local" || (session?.organizationId === "demo" && session.isDemo));
}
