"use client";

import type { ProfileSummary } from "@/lib/api";
import { useClient } from "./client-context";
import Icon from "./ui/icon";

/**
 * 侧边栏客户选择器 —— profiles 由根布局服务端注入；
 * 选择写入全局客户上下文并持久化。
 */
export default function ClientSelector({
  profiles,
}: {
  profiles: ProfileSummary[];
}) {
  const { clientId, select, clear } = useClient();
  if (profiles.length === 0) return null;

  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-medium tracking-[0.18em] text-mist-600 uppercase">
        <Icon name="users" size={11} />
        当前客户
      </div>
      <div className="relative">
        <select
          value={clientId ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) {
              clear();
              return;
            }
            const p = profiles.find((p) => p.id === Number(v));
            if (p) select(p.id, p.name);
          }}
          className="w-full appearance-none rounded-lg border border-white/[0.08] bg-ink-850/70 py-2 pr-8 pl-3 text-sm text-mist-200 transition-all duration-300 ease-luxe outline-none focus:border-gold-500/45"
        >
          <option value="">未选择客户</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <Icon
          name="chevronDown"
          size={13}
          className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-mist-500"
        />
      </div>
    </div>
  );
}
