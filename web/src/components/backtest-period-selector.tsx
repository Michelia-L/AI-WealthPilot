"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import Segmented from "./ui/segmented";

const OPTIONS = [
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" },
];

/** 回测窗口切换 —— ?doc=X&bt=Y，保留文档参数导航。 */
export default function BacktestPeriodSelector({
  documentId,
  period,
}: {
  documentId: string;
  period: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <span className={pending ? "opacity-60 transition-opacity" : ""}>
      <Segmented
        size="sm"
        options={OPTIONS}
        value={period}
        onChange={(v) =>
          startTransition(() => {
            router.push(
              `/monitoring?doc=${encodeURIComponent(documentId)}&bt=${v}`,
              { scroll: false }
            );
          })
        }
      />
    </span>
  );
}
