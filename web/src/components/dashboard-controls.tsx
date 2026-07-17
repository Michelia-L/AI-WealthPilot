"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { DEFAULT_PERIOD, PERIOD_OPTIONS } from "@/lib/api";

interface DashboardControlsProps {
  categories: string[];
  selectedCategories: string[];
  period: string;
  assetCount: number;
}

/**
 * Control bar for the dashboard. Filter state lives in the URL query string
 * (?period=&categories=), so selections are shareable and the page stays
 * server-rendered — this component only triggers RSC navigations.
 */
export default function DashboardControls({
  categories,
  selectedCategories,
  period,
  assetCount,
}: DashboardControlsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function navigate(nextCategories: string[], nextPeriod: string) {
    const params = new URLSearchParams();
    if (nextPeriod !== DEFAULT_PERIOD) params.set("period", nextPeriod);
    if (nextCategories.length !== categories.length) {
      params.set("categories", nextCategories.join(","));
    }
    const qs = params.toString();
    startTransition(() => {
      router.push(qs ? `/?${qs}` : "/", { scroll: false });
    });
  }

  function toggleCategory(category: string) {
    const isOn = selectedCategories.includes(category);
    // Prevent deselecting the last category — an empty universe is useless.
    if (isOn && selectedCategories.length === 1) return;
    navigate(
      isOn
        ? selectedCategories.filter((c) => c !== category)
        : [...selectedCategories, category],
      period
    );
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 transition-opacity ${
        pending ? "opacity-60" : ""
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          资产类别
        </span>
        {categories.map((c) => {
          const active = selectedCategories.includes(c);
          return (
            <button
              key={c}
              onClick={() => toggleCategory(c)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
                  : "border-slate-700 bg-transparent text-slate-500 hover:border-slate-600 hover:text-slate-300"
              }`}
            >
              {c}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          视窗
        </span>
        <div className="flex overflow-hidden rounded-lg border border-slate-700">
          {PERIOD_OPTIONS.map((p) => (
            <button
              key={p.value}
              onClick={() => navigate(selectedCategories, p.value)}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                period === p.value
                  ? "bg-slate-700 text-slate-100"
                  : "bg-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <span className="ml-2 text-xs text-slate-500">
          {pending ? "刷新中…" : `${assetCount} 个资产`}
        </span>
      </div>
    </div>
  );
}
