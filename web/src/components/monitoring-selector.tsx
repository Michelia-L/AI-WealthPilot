"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type { IpsDocumentSummary } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtLocal } from "@/lib/format";
import { useT } from "@/components/locale-context";
import { useClient } from "@/components/client-context";
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
  const { clientId, clientName } = useClient();
  const [pending, startTransition] = useTransition();
  const [scope, setScope] = useState<{ clientId: number | null; all: boolean } | null>(null);
  const copy = t.common.monitoringSelector;
  const current = documents.filter((d) => clientId !== null && d.profile_id === clientId);
  const others = documents.filter((d) => d.profile_id != null && d.profile_id !== clientId);
  const unlinked = documents.filter((d) => d.profile_id == null);
  // A direct document link remains visible, even when it belongs to another
  // client. Otherwise default to the active client's documents after hydration.
  const showAll = clientId === null || (scope?.clientId === clientId
    ? scope.all
    : Boolean(selected && !current.some((d) => d.document_id === selected)));

  function option(d: IpsDocumentSummary) {
    const suffix = d.document_id.slice(-8);
    const unique = documents.filter((other) => other.document_id.endsWith(suffix)).length === 1;
    return (
      <option key={d.document_id} value={d.document_id}>
        {d.client_name} · v{d.version} · {d.status} · {fmtLocal(d.saved_at)} · {unique ? suffix : d.document_id}
      </option>
    );
  }

  return (
    <div
      className={cx(
        "flex flex-col gap-3 rounded-xl border border-white/[0.06] bg-ink-900/70 px-4 py-3 transition-opacity duration-300",
        pending && "opacity-60"
      )}
    >
      {clientId !== null && (
        <Field label={copy.clientFilter}>
          <Select
            value={showAll ? "all" : "current"}
            onChange={(e) => {
              const all = e.target.value === "all";
              setScope({ clientId, all });
              if (!all && selected && !current.some((d) => d.document_id === selected)) {
                startTransition(() => router.push("/monitoring"));
              }
            }}
          >
            <option value="current">{copy.currentClient(clientName ?? String(clientId))}</option>
            <option value="all">{copy.allClients}</option>
          </Select>
        </Field>
      )}
      <Field label={t.common.monitoringSelector.label}>
        <Select
          value={showAll || current.some((d) => d.document_id === selected) ? selected : ""}
          onChange={(e) => {
            const v = e.target.value;
            startTransition(() => {
              router.push(v ? `/monitoring?doc=${encodeURIComponent(v)}` : "/monitoring");
            });
          }}
        >
          <option value="">{t.common.monitoringSelector.placeholder}</option>
          {current.length > 0 && (
            <optgroup label={copy.currentClient(clientName ?? String(clientId))}>
              {current.map(option)}
            </optgroup>
          )}
          {showAll && others.length > 0 && (
            <optgroup label={copy.otherClients}>{others.map(option)}</optgroup>
          )}
          {showAll && unlinked.length > 0 && (
            <optgroup label={copy.unlinked}>{unlinked.map(option)}</optgroup>
          )}
        </Select>
      </Field>
      {!showAll && current.length === 0 && (
        <p className="text-xs text-mist-400" role="status">{copy.noClientDocuments}</p>
      )}
      {unlinked.length > 0 && (
        <p className="text-xs text-mist-500">{copy.unlinkedHint}</p>
      )}
    </div>
  );
}
