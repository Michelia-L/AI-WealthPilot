"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/components/locale-context";
import Button from "@/components/ui/button";

export default function AcknowledgeDocument({
  id,
  acknowledged,
}: {
  id: string;
  acknowledged: boolean;
}) {
  const t = useT().clientPortal;
  const router = useRouter();
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/me/reports/${encodeURIComponent(id)}/acknowledge`,
        { method: "POST" },
      );
      const data = await response.json().catch(() => null);
      if (!response.ok || data?.status !== "acknowledged") {
        setError(
          typeof data?.detail === "string" ? data.detail : t.acknowledgeFailed,
        );
        return;
      }
      setConfirmed(true);
      router.refresh();
    } catch {
      setError(t.acknowledgeFailed);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs leading-6 text-mist-400">{t.acknowledgeHint}</p>
      {acknowledged || confirmed ? (
        <p role="status" className="text-sm text-jade-300">
          {t.statuses.acknowledged}
        </p>
      ) : (
        <Button icon="check" disabled={pending} onClick={() => void confirm()}>
          {pending ? t.acknowledging : t.acknowledge}
        </Button>
      )}
      {error && (
        <p role="alert" className="text-sm text-cinnabar-300">
          {error}
        </p>
      )}
    </div>
  );
}
