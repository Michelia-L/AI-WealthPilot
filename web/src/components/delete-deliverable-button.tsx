"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useT } from "@/components/locale-context";
import Button from "@/components/ui/button";
import ConfirmDialog from "@/components/ui/confirm-dialog";

export default function DeleteDeliverableButton({
  kind,
  id,
  clientName,
  onDeleted,
}: {
  kind: "advisor" | "ips";
  id: string;
  clientName: string;
  onDeleted?: () => void;
}) {
  const t = useT();
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function remove() {
    if (inFlight.current) return;
    inFlight.current = true;
    setConfirming(false);
    setPending(true);
    setError(null);
    const base = kind === "ips" ? "/api/ips" : "/api/advisor/reports";
    try {
      const res = await fetch(`${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(typeof data?.detail === "string" ? data.detail : t.deliverables.deleteFailed);
        return;
      }
      onDeleted?.();
      router.refresh();
    } catch {
      setError(t.deliverables.deleteFailed);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        variant="danger"
        size="sm"
        icon="trash"
        disabled={pending}
        aria-label={t.deliverables.deleteLabel(clientName)}
        onClick={() => setConfirming(true)}
      >
        {pending ? t.deliverables.deleting : t.common.delete}
      </Button>
      {error && <p role="alert" className="max-w-64 text-sm text-cinnabar-400">{error}</p>}
      <ConfirmDialog
        open={confirming}
        title={t.deliverables.deleteTitle}
        description={t.deliverables.deleteDescription(clientName)}
        confirmLabel={t.common.delete}
        danger
        onConfirm={() => void remove()}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
