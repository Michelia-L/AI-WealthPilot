"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type {
  AdvisorStatusResponse,
  IpsDocumentSummary,
  ProfileSummary,
} from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import { readSseStream } from "@/lib/sse";
import Markdown from "@/components/markdown";
import { useClient } from "@/components/client-context";
import Button from "@/components/ui/button";
import { Badge } from "@/components/ui/chip";
import EmptyState from "@/components/ui/empty";
import { Field, Select } from "@/components/ui/field";
import Icon from "@/components/ui/icon";
import Panel from "@/components/ui/panel";
import Segmented from "@/components/ui/segmented";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";

interface ProgressStep {
  node: string;
  label: string;
}

interface DoneInfo {
  document_id: string;
  status: string;
  revision_count: number;
}

const MAX_REVISION_OPTIONS = [0, 1, 2, 3];

const REVISION_SEGMENT_OPTIONS = MAX_REVISION_OPTIONS.map((n) => ({
  value: n,
  label: String(n),
}));

export default function IpsWorkspace({
  profiles,
  status,
  initialDocuments,
}: {
  profiles: ProfileSummary[] | null;
  status: AdvisorStatusResponse | null;
  initialDocuments: IpsDocumentSummary[];
}) {
  const router = useRouter();
  const { clientId, select } = useClient();
  const [selectedId, setSelectedId] = useState<number | null>(profiles?.[0]?.id ?? null);
  const [maxRevisions, setMaxRevisions] = useState(3);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [doneInfo, setDoneInfo] = useState<DoneInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{
    documentId: string;
    title: string;
    version: string;
    status: string;
    revisionRounds: number;
    markdown: string;
  } | null>(null);

  const configured = status?.configured ?? false;

  // 全局客户上下文仅应用一次作为默认选中（render 期条件调整，React 官方模式）；
  // 此后以本页选择为准并回写上下文。
  const [appliedGlobalDefault, setAppliedGlobalDefault] = useState(false);
  if (
    !appliedGlobalDefault &&
    clientId !== null &&
    profiles?.some((p) => p.id === clientId)
  ) {
    setAppliedGlobalDefault(true);
    setSelectedId(clientId);
  }

  function handleSelectProfile(id: number) {
    setSelectedId(id);
    const p = profiles?.find((profile) => profile.id === id);
    if (p) select(p.id, p.name);
  }

  async function generate() {
    if (selectedId === null) return;
    setRunning(true);
    setSteps([]);
    setDoneInfo(null);
    setError(null);
    setViewing(null);

    try {
      const res = await fetch("/api/ips/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: selectedId, max_revisions: maxRevisions }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : `创建任务失败（HTTP ${res.status}）`);
      }

      const eventsRes = await fetch(`/api/ips/tasks/${data.task_id}/events`);
      if (!eventsRes.ok || !eventsRes.body) {
        const err = await eventsRes.json().catch(() => null);
        throw new Error(err && typeof err.detail === "string" ? err.detail : "无法接收任务进度");
      }
      await readSseStream(eventsRes.body, (event) => {
        if (event.type === "node") {
          setSteps((prev) => [...prev, { node: String(event.node), label: String(event.label) }]);
        } else if (event.type === "done") {
          setDoneInfo({
            document_id: String(event.document_id),
            status: String(event.status ?? ""),
            revision_count: Number(event.revision_count ?? 0),
          });
        } else if (event.type === "error") {
          setError(String(event.message ?? "生成失败"));
        }
      });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  async function viewDocument(doc: IpsDocumentSummary) {
    setError(null);
    try {
      const res = await fetch(`/api/ips/${encodeURIComponent(doc.document_id)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
      setViewing({
        documentId: doc.document_id,
        title: `${doc.client_name} · v${doc.version}`,
        version: doc.version,
        status: doc.status,
        revisionRounds: doc.revision_rounds,
        markdown: data.markdown,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="mt-10 flex flex-col gap-8">
      {/* ------------------------------ 生成控制 ------------------------------ */}
      <Panel>
        {!configured && (
          <div className="mb-5 flex items-start gap-3 rounded-xl border border-gold-500/25 bg-gold-500/[0.07] px-4 py-3 text-sm text-gold-300">
            <Icon name="warning" size={16} className="mt-0.5 shrink-0 text-gold-400" />
            <span>
              DEEPSEEK_API_KEY 未配置 —— 请在项目根目录 .env 中设置并重启 API 服务后使用。
            </span>
          </div>
        )}

        {profiles === null ? (
          <p className="flex items-center gap-2 text-sm text-cinnabar-400">
            <Icon name="warning" size={14} />
            无法获取画像列表 —— 请确认 API 服务已启动。
          </p>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-mist-400">
            还没有客户画像。请先在
            <Link
              href="/profiles"
              className="mx-1 text-gold-400 underline underline-offset-4 hover:text-gold-300"
            >
              客户画像
            </Link>
            页面创建。
          </p>
        ) : (
          <div className="flex flex-wrap items-end gap-x-8 gap-y-5">
            <Field label="选择画像" className="min-w-64">
              <Select
                value={selectedId ?? ""}
                onChange={(e) => handleSelectProfile(Number(e.target.value))}
                disabled={running}
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}（{p.age} 岁{p.risk_level ? ` · ${p.risk_level.split(" / ")[1] ?? p.risk_level}` : ""}）
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="最大修订轮数">
              <div className={running ? "pointer-events-none opacity-50" : undefined}>
                <Segmented
                  options={REVISION_SEGMENT_OPTIONS}
                  value={maxRevisions}
                  onChange={setMaxRevisions}
                />
              </div>
            </Field>

            <Button
              size="lg"
              icon="scroll"
              onClick={generate}
              disabled={running || !configured || selectedId === null}
            >
              {running ? "工作流运行中…" : "生成 IPS"}
            </Button>

            <p className="max-w-60 pb-1 text-xs leading-5 text-mist-600">
              CME → 初稿 → 三维评审 → SAA 量化验证 → 修订/定稿（通常需要数分钟）
            </p>
          </div>
        )}

        {error && (
          <p className="mt-5 flex items-center gap-2 text-sm text-cinnabar-400">
            <Icon name="warning" size={14} />
            {error}
          </p>
        )}
      </Panel>

      {/* ------------------------------ 进度时间线 ------------------------------ */}
      {(steps.length > 0 || running) && (
        <Panel>
          <h3 className="mb-4 text-sm font-semibold text-mist-100">工作流进度</h3>
          <ol className="space-y-3">
            {steps.map((s, i) => (
              <li key={`${s.node}-${i}`} className="flex items-center gap-3 text-sm">
                <Icon name="check" size={14} className="text-jade-400" />
                <span className="text-mist-200">{s.label}</span>
              </li>
            ))}
            {running && (
              <li className="flex items-center gap-3 text-sm">
                <span className="flex w-3.5 items-center justify-center">
                  <span className="h-1.5 w-1.5 rounded-full bg-gold-400 animate-pulse-dot" />
                </span>
                <span className="text-gold-300">正在处理…</span>
              </li>
            )}
          </ol>

          {doneInfo && (
            <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-3 rounded-xl border border-jade-500/25 bg-jade-500/[0.07] px-4 py-3">
              <Icon name="check" size={15} className="shrink-0 text-jade-400" />
              <p className="text-sm text-jade-300">
                IPS 已生成并入库 · 文档{" "}
                <span className="font-mono text-xs">{doneInfo.document_id}</span> ·
                状态 {doneInfo.status}
                {doneInfo.revision_count > 0 ? ` · 修订 ${doneInfo.revision_count} 轮` : ""}
              </p>
              <Button
                size="sm"
                variant="secondary"
                className="ml-auto"
                onClick={() =>
                  viewDocument({
                    document_id: doneInfo.document_id,
                    client_name:
                      profiles?.find((p) => p.id === selectedId)?.name ?? "",
                    version: "?",
                    risk_level: "",
                    status: doneInfo.status,
                    revision_rounds: doneInfo.revision_count,
                    saved_at: "",
                  })
                }
              >
                立即查看
              </Button>
            </div>
          )}
        </Panel>
      )}

      {/* ------------------------------ 文档查看 ------------------------------ */}
      {viewing && (
        <Panel>
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="font-display text-xl text-mist-100">{viewing.title}</h3>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-mist-500">
                <span>
                  版本 <span className="font-mono text-mist-300">{viewing.version}</span>
                </span>
                <Badge tone={viewing.status === "approved" ? "jade" : "gold"} dot>
                  {viewing.status || "unknown"}
                </Badge>
                <span>
                  修订轮次 <span className="tnum text-mist-300">{viewing.revisionRounds}</span>
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <a href={`/api/ips/${encodeURIComponent(viewing.documentId)}/pdf`}>
                <Button variant="secondary" size="sm" trailingIcon="download">
                  下载 PDF
                </Button>
              </a>
              <Button variant="ghost" size="sm" icon="x" onClick={() => setViewing(null)}>
                关闭
              </Button>
            </div>
          </div>
          <Markdown>{viewing.markdown}</Markdown>
        </Panel>
      )}

      {/* ------------------------------ 文档库 ------------------------------ */}
      <section>
        <div className="mb-4 flex items-baseline gap-3">
          <h2 className="font-display text-xl text-mist-100">IPS 文档库</h2>
          <span className="text-xs text-mist-500">本地 JSON 存储</span>
        </div>
        {initialDocuments.length === 0 ? (
          <Panel pad={false}>
            <EmptyState
              icon="scroll"
              title="暂无 IPS 文档"
              hint="选择客户画像并运行上方工作流后，生成的 IPS 文档将保存在这里。"
            />
          </Panel>
        ) : (
          <Panel pad={false} innerClassName="overflow-hidden">
            <Table className="min-w-[760px]">
              <THead>
                <tr>
                  <TH>客户</TH>
                  <TH>版本</TH>
                  <TH>风险等级</TH>
                  <TH>状态</TH>
                  <TH className="text-right">修订轮数</TH>
                  <TH>保存时间</TH>
                  <TH className="text-right">操作</TH>
                </tr>
              </THead>
              <tbody>
                {initialDocuments.map((d) => (
                  <TR key={d.document_id}>
                    <TD className="font-medium text-mist-100">{d.client_name}</TD>
                    <TD className="font-mono text-xs">{d.version}</TD>
                    <TD>
                      {d.risk_level ? (
                        <Badge tone="steel">{d.risk_level}</Badge>
                      ) : (
                        <span className="text-mist-600">—</span>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={d.status === "approved" ? "jade" : "gold"} dot>
                        {d.status}
                      </Badge>
                    </TD>
                    <TD className="text-right font-mono">{d.revision_rounds}</TD>
                    <TD className="font-mono text-xs text-mist-500">
                      {fmtLocal(d.saved_at)}
                    </TD>
                    <TD className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="eye"
                          onClick={() => viewDocument(d)}
                        >
                          查看
                        </Button>
                        <a href={`/api/ips/${encodeURIComponent(d.document_id)}/pdf`}>
                          <Button variant="secondary" size="sm" trailingIcon="download">
                            PDF
                          </Button>
                        </a>
                      </div>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Panel>
        )}
      </section>
    </div>
  );
}
