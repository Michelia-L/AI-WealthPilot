"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { DEFAULT_PERIOD, PERIOD_OPTIONS } from "@/lib/api";
import { cx } from "@/lib/cx";
import { Chip } from "./ui/chip";
import Segmented from "./ui/segmented";

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
      router.push(qs ? `/market?${qs}` : "/market", { scroll: false });
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
      className={cx(
        "flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-white/[0.06] bg-ink-900/70 px-4 py-3 transition-opacity duration-300",
        pending && "opacity-60"
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          资产类别
        </span>
        {categories.map((c) => (
          <Chip
            key={c}
            selected={selectedCategories.includes(c)}
            onClick={() => toggleCategory(c)}
          >
            {c}
          </Chip>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          视窗
        </span>
        <Segmented
          size="sm"
          options={PERIOD_OPTIONS}
          value={period}
          onChange={(v) => navigate(selectedCategories, v)}
        />
        <span className="text-xs text-mist-500">
          {pending ? "刷新中…" : `${assetCount} 个资产`}
        </span>
      </div>
    </div>
  );
}
