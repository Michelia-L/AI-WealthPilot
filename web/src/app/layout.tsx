import { getWorkspaceSession } from "@/lib/session";
import WorkspaceSessionControl from "@/components/workspace-session";
import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { LocaleProvider } from "@/components/locale-context";
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

  return (
    <html
      lang={locale === "zh" ? "zh-CN" : "en"}
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <LocaleProvider locale={locale}>
          {!session?.organizationId ? (
            <WorkspaceSessionControl session={session} gate />
          ) : (
            children
          )}
        </LocaleProvider>
      </body>
    </html>
  );
}
