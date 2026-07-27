"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { cx } from "@/lib/cx";
import { useT } from "@/components/locale-context";
import Segmented from "./ui/segmented";
import { Select } from "./ui/field";

interface DeliverablesControlsProps {
  clients: string[];
  client: string; // "" = 全部
  type: string; // "all" | "advisor" | "ips"
  total: number;
}

/**
 * 交付物筛选栏 —— 筛选态存于 URL（?client=&type=），
 * 与仪表盘一致的 RSC 导航模式。
 */
export default function DeliverablesControls({
  clients,
  client,
  type,
  total,
}: DeliverablesControlsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const t = useT();

  function navigate(nextClient: string, nextType: string) {
    const params = new URLSearchParams();
    if (nextClient) params.set("client", nextClient);
    if (nextType !== "all") params.set("type", nextType);
    const qs = params.toString();
    startTransition(() => {
      router.push(qs ? `/deliverables?${qs}` : "/deliverables", {
        scroll: false,
      });
    });
  }

  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-white/[0.06] bg-ink-900/70 px-4 py-3 transition-opacity duration-300",
        pending && "opacity-60"
      )}
    >
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          {t.deliverables.filterClient}
        </span>
        <Select
          value={client}
          onChange={(e) => navigate(e.target.value, type)}
          className="w-44"
        >
          <option value="">{t.deliverables.allClients}</option>
          {clients.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          {t.deliverables.filterType}
        </span>
        <Segmented
          size="sm"
          options={[
            { value: "all", label: t.deliverables.typeAll },
            { value: "advisor", label: t.deliverables.kindAdvisor },
            { value: "ips", label: t.deliverables.typeIps },
          ]}
          value={type}
          onChange={(v) => navigate(client, v)}
        />
        <span className="text-xs text-mist-500">
          {pending ? t.deliverables.refreshing : t.deliverables.countLabel(total)}
        </span>
      </div>
    </div>
  );
}
