"use client";

import { Fragment } from "react";
import { useClient } from "./client-context";
import { useT } from "./locale-context";

/** Reset forms/results and disconnect streams when their client changes. */
export default function ClientWorkspace({ children }: { children: React.ReactNode }) {
  const { ready, taskScope, clientName } = useClient();
  const t = useT();
  if (!ready) return null;
  return <>
    <p className="mb-4 text-sm text-mist-400" role="status">
      {clientName ? `${t.clientSelector.label}: ${clientName}` : t.clientSelector.required}
    </p>
    <Fragment key={taskScope}>{children}</Fragment>
  </>;
}
