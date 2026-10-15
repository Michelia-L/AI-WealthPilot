import type { Metadata } from "next";
import { redirect } from "next/navigation";
import ClientPortalShell from "@/components/client-portal/shell";
import ClientUnavailable from "@/components/client-portal/unavailable";
import LocaleSwitcher from "@/components/locale-switcher";
import WorkspaceSessionControl from "@/components/workspace-session";
import { getClientIdentity } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";
import { getWorkspaceSession, workspaceRole } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = (await getDict()).clientPortal;
  return { title: `${t.name} · WealthPilot` };
}

export default async function ClientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getWorkspaceSession();
  if (!session?.organizationId) return null;
  if (workspaceRole(session) !== "client") redirect("/");
  const identity = await getClientIdentity(await getLocale());
  if (!identity.data)
    return (
      <div className="mx-auto my-20 max-w-lg space-y-5 px-5">
        <LocaleSwitcher />
        <ClientUnavailable access />
        <WorkspaceSessionControl session={session} />
      </div>
    );
  return (
    <ClientPortalShell
      isDemo={identity.data.is_demo}
      sessionControls={<WorkspaceSessionControl session={session} />}
    >
      {children}
    </ClientPortalShell>
  );
}
