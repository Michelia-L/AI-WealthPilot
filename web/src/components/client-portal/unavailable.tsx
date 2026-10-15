"use client";

import { useRouter } from "next/navigation";
import { useT } from "@/components/locale-context";
import { Button, Panel } from "@/components/ui";

export default function ClientUnavailable({
  access = false,
}: {
  access?: boolean;
}) {
  const t = useT().clientPortal;
  const router = useRouter();
  return (
    <Panel>
      <p role="alert" className="text-sm leading-6 text-mist-300">
        {access ? t.accessUnavailable : t.unavailable}
      </p>
      <Button
        className="mt-4"
        size="sm"
        variant="secondary"
        icon="refresh"
        onClick={() => router.refresh()}
      >
        {t.retry}
      </Button>
    </Panel>
  );
}
