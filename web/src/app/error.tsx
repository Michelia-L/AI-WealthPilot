"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { useT } from "@/components/locale-context";
import { Button, Icon, Panel } from "@/components/ui";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  const t = useT();

  useEffect(() => {
    // Keep the error in the console for debugging; digest links to server logs.
    console.error(error);
  }, [error]);

  return (
    <Panel className="border-gold-700/40 bg-gold-500/[0.06] p-8">
      <p className="flex items-center gap-2 font-medium text-gold-200/90">
        <Icon name="warning" size={16} className="shrink-0 text-gold-400" />
        {t.errors.page.errorTitle}
      </p>
      <p className="mt-2 text-sm leading-6 text-gold-200/60">
        {t.errors.page.errorHint}
      </p>
      {error.digest && (
        <p className="mt-3 font-mono text-xs text-mist-500">
          digest: {error.digest}
        </p>
      )}
      <div className="mt-5">
        <Button size="sm" onClick={() => unstable_retry()}>
          {t.errors.page.retry}
        </Button>
      </div>
    </Panel>
  );
}
