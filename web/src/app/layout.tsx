import { getWorkspaceSession, workspaceRole, canManageSettings } from "@/lib/session";
import WorkspaceSessionControl from "@/components/workspace-session";
import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, IBM_Plex_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "@/components/app-shell";
import { ClientProvider } from "@/components/client-context";
import HealthBadge from "@/components/health-badge";
import { LocaleProvider } from "@/components/locale-context";
import { getProfiles } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/** 展示衬线 —— 编辑级标题（拉丁部分；中文走 Songti/Noto Serif 栈） */
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz"],
});

/** 数字/表格等宽 */
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return {
    title: t.meta.title,
    description: t.meta.description,
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const [locale, session] = await Promise.all([getLocale(), getWorkspaceSession()]);
  const role = workspaceRole(session);
  const isAdvisor = role === "advisor" || role === "admin";
  const profilesData = isAdvisor ? await getProfiles() : null;
  const profiles = profilesData?.profiles ?? [];
  const t = await getDict();

  return (
    <html
      lang={locale === "zh" ? "zh-CN" : "en"}
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ClientProvider profiles={profiles} scope={session ? `${session.userId}:${session.organizationId}` : "signed-out"}>
          <LocaleProvider locale={locale}>
            {!session?.organizationId ? (
              <WorkspaceSessionControl session={session} gate />
            ) : !isAdvisor ? (
              <div className="mx-auto my-24 max-w-lg space-y-5 px-5">
                <h1 className="font-display text-2xl">{t.nav.console}</h1>
                <p role="alert">{t.auth.advisorOnly}</p>
                <WorkspaceSessionControl session={session} />
              </div>
            ) : (
              <AppShell
                canManageSettings={canManageSettings(session)}
                sessionControls={<WorkspaceSessionControl session={session} />}
                profiles={profiles}
                healthBadge={
                  <Suspense
                    fallback={
                      <span className="inline-block h-6 w-24 animate-pulse rounded-full bg-ink-800" />
                    }
                  >
                    <HealthBadge />
                  </Suspense>
                }
              >
                {children}
              </AppShell>
            )}
          </LocaleProvider>
        </ClientProvider>
      </body>
    </html>
  );
}
