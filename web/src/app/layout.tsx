import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, IBM_Plex_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "@/components/app-shell";
import { ClientProvider } from "@/components/client-context";
import HealthBadge from "@/components/health-badge";
import { LocaleProvider } from "@/components/locale-context";
import { getProfiles } from "@/lib/api";
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
  const [profilesData, locale] = await Promise.all([getProfiles(), getLocale()]);

  return (
    <html
      lang={locale === "zh" ? "zh-CN" : "en"}
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ClientProvider>
          <LocaleProvider locale={locale}>
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
          </LocaleProvider>
        </ClientProvider>
      </body>
    </html>
  );
}
