"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import type { IpsDocumentSummary } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtLocal } from "@/lib/format";
import { useT } from "@/components/locale-context";
import { Field, Select } from "./ui/field";

/**
 * 监控文档选择器 —— 选择存入的 IPS 文档，?doc=<id> 写入 URL，
 * 页面保持服务端渲染。
 */
export default function MonitoringSelector({
  documents,
  selected,
}: {
  documents: IpsDocumentSummary[];
  selected: string;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <div
      className={cx(
        "rounded-xl border border-white/[0.06] bg-ink-900/70 px-4 py-3 transition-opacity duration-300",
        pending && "opacity-60"
      )}
    >
      <Field label={t.common.monitoringSelector.label}>
        <Select
          value={selected}
          onChange={(e) => {
            const v = e.target.value;
            startTransition(() => {
              router.push(v ? `/monitoring?doc=${encodeURIComponent(v)}` : "/monitoring");
            });
          }}
        >
          <option value="">{t.common.monitoringSelector.placeholder}</option>
          {documents.map((d) => (
            <option key={d.document_id} value={d.document_id}>
              {d.client_name} · v{d.version} · {d.status} · {fmtLocal(d.saved_at)}
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );
}
