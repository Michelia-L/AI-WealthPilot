import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import NavSidebar from "@/components/nav-sidebar";
import HealthBadge from "@/components/health-badge";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI WealthPilot",
  description:
    "AI-assisted private wealth management — quantitative portfolio engine and advisor agents.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <div className="flex min-h-screen">
          <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-slate-800 bg-slate-950/60 px-4 py-6">
            <div className="mb-8 px-2">
              <div className="text-lg font-bold tracking-tight text-slate-50">
                AI WealthPilot
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                Intelligent Wealth Management
              </div>
            </div>

            <NavSidebar />

            <div className="mt-auto px-2">
              <Suspense
                fallback={
                  <span className="inline-block h-6 w-24 animate-pulse rounded-full bg-slate-800" />
                }
              >
                <HealthBadge />
              </Suspense>
            </div>
          </aside>

          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
