"use client";

import { Fragment } from "react";
import { useClient } from "./client-context";
import { useT } from "./locale-context";

/** Reset forms/results and disconnect streams when their client changes. */
export default function ClientWorkspace({ children, manual = false }: { children: React.ReactNode; manual?: boolean }) {
  const { ready, taskScope, clientName } = useClient();
  const t = useT();
  if (!ready) return null;
  return <>
    <p className="mb-4 text-sm text-mist-400" role="status">
      {clientName ? `${t.clientSelector.label}: ${clientName}` : manual ? t.clientSelector.manual : t.clientSelector.empty}
    </p>
    <Fragment key={taskScope}>{children}</Fragment>
  </>;
}
