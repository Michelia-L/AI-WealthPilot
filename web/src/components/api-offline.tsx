"use client";

import { useT } from "@/components/locale-context";
import Icon from "./ui/icon";

/** Shared panel shown when the FastAPI backend is unreachable. */
export function ApiOffline({ resource }: { resource: string }) {
  const t = useT();
  return (
    <div className="rounded-xl border border-gold-700/40 bg-gold-500/[0.06] p-6 text-sm text-gold-200/90">
      <p className="flex items-center gap-2 font-medium">
        <Icon name="warning" size={15} className="shrink-0 text-gold-400" />
        {t.errors.offline.unreachable(resource)}
      </p>
      <p className="mt-2 leading-6 text-gold-200/60">
        {t.errors.offline.startBackend}
        <code className="mx-1 rounded bg-ink-800 px-1.5 py-0.5 font-mono text-xs text-gold-200">
          uvicorn api.main:app --port 8000
        </code>
        {t.errors.offline.or}
        <code className="mx-1 rounded bg-ink-800 px-1.5 py-0.5 font-mono text-xs text-gold-200">
          docker compose up
        </code>
      </p>
    </div>
  );
}
