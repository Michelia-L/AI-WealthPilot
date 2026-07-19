import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, IBM_Plex_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "@/components/app-shell";
import { ClientProvider } from "@/components/client-context";
import HealthBadge from "@/components/health-badge";
import { getProfiles } from "@/lib/api";

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

export const metadata: Metadata = {
  title: "AI WealthPilot · 私人财富管理工作站",
  description:
    "AI 辅助的私人财富管理工作站 —— 量化组合引擎、资本市场预期与顾问智能体。",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const profilesData = await getProfiles();

  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ClientProvider>
          <AppShell
            profiles={profilesData?.profiles ?? []}
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
        </ClientProvider>
      </body>
    </html>
  );
}
