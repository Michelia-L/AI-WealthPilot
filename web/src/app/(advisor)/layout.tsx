import { Suspense } from "react";
import { redirect } from "next/navigation";
import AppShell from "@/components/app-shell";
import { ClientProvider } from "@/components/client-context";
import HealthBadge from "@/components/health-badge";
import WorkspaceSessionControl from "@/components/workspace-session";
import { getProfiles } from "@/lib/api/server";
import { getDict } from "@/lib/i18n/server";
import {
  canManageSettings,
  getWorkspaceSession,
  workspaceRole,
} from "@/lib/session";

export default async function AdvisorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getWorkspaceSession();
  if (!session?.organizationId) return null;
  const role = workspaceRole(session);
  if (role === "client") redirect("/client");
  if (role !== "advisor" && role !== "admin") {
    const t = await getDict();
    return <p role="alert">{t.auth.advisorOnly}</p>;
  }
  const profiles = (await getProfiles())?.profiles ?? [];
  return (
    <ClientProvider
      profiles={profiles}
      scope={`${session.userId}:${session.organizationId}`}
    >
      <AppShell
        profiles={profiles}
        canManageSettings={canManageSettings(session)}
        sessionControls={<WorkspaceSessionControl session={session} />}
        healthBadge={
          <Suspense fallback={null}>
            <HealthBadge />
          </Suspense>
        }
      >
        {children}
      </AppShell>
    </ClientProvider>
  );
}
