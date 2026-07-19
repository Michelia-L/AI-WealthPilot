"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { cx } from "@/lib/cx";
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
          客户
        </span>
        <Select
          value={client}
          onChange={(e) => navigate(e.target.value, type)}
          className="w-44"
        >
          <option value="">全部客户</option>
          {clients.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
          类型
        </span>
        <Segmented
          size="sm"
          options={[
            { value: "all", label: "全部" },
            { value: "advisor", label: "AI 建议书" },
            { value: "ips", label: "IPS 文档" },
          ]}
          value={type}
          onChange={(v) => navigate(client, v)}
        />
        <span className="text-xs text-mist-500">
          {pending ? "刷新中…" : `${total} 份`}
        </span>
      </div>
    </div>
  );
}
