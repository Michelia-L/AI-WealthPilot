"use client";

import { useRouter } from "next/navigation";
import { useClient } from "@/components/client-context";
import { useT } from "@/components/locale-context";
import { Button } from "@/components/ui";

/**
 * 客户枢纽操作区 —— 设为当前客户（写入全局上下文）、
 * 携带客户上下文跳转 AI 顾问 / IPS 生成。
 */
export default function HubActions({
  id,
  name,
}: {
  id: number;
  name: string;
}) {
  const router = useRouter();
  const t = useT();
  const { clientId, select, clear } = useClient();
  const isCurrent = clientId === id;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant={isCurrent ? "secondary" : "ghost"}
        icon={isCurrent ? "check" : "users"}
        onClick={() => (isCurrent ? clear() : select(id, name))}
      >
        {isCurrent
          ? t.profileDetail.currentClient
          : t.profileDetail.setAsCurrentClient}
      </Button>
      <Button
        icon="sparkle"
        onClick={() => {
          select(id, name);
          router.push("/advisor");
        }}
      >
        {t.profileDetail.generateReport}
      </Button>
      <Button
        variant="secondary"
        icon="scroll"
        onClick={() => {
          select(id, name);
          router.push("/ips");
        }}
      >
        {t.profileDetail.generateIps}
      </Button>
    </div>
  );
}
