"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type {
  AdvisorDoneEvent,
  AdvisorStatusResponse,
  ProfileSummary,
  ReportSummary,
} from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import { readSseStream } from "@/lib/sse";
import Markdown from "@/components/markdown";
import { useClient } from "@/components/client-context";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Icon,
  Input,
  Panel,
  Select,
  Table,
  TD,
  TH,
  THead,
  TR,
  Textarea,
} from "@/components/ui";

export default function AdvisorWorkspace({
  profiles,
  status,
  initialReports,
}: {
  profiles: ProfileSummary[] | null;
  status: AdvisorStatusResponse | null;
  initialReports: ReportSummary[];
}) {
  const router = useRouter();
  const { clientId, select } = useClient();
  // 用户手动选择的画像；未选择时回退到全局客户上下文，再回退到列表首位。
  // 纯派生，不用 effect —— 手动选择一旦存在便永远优先，上下文只作默认。
  const [pickedId, setPickedId] = useState<number | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState("");
  const [done, setDone] = useState<AdvisorDoneEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [clientName, setClientName] = useState("");
  const [notes, setNotes] = useState("");
  const [viewing, setViewing] = useState<{ title: string; content: string } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 默认选中：全局上下文中的客户（须在画像列表中），否则列表首位
  const contextDefaultId =
    clientId !== null && profiles?.some((p) => p.id === clientId) ? clientId : null;
  const selectedId = pickedId ?? contextDefaultId ?? profiles?.[0]?.id ?? null;

  function handleSelect(id: number) {
    setPickedId(id);
    const p = profiles?.find((profile) => profile.id === id);
    if (p) select(p.id, p.name);
  }

  async function generate() {
    if (selectedId === null) return;
    setStreaming(true);
    setText("");
    setDone(null);
    setError(null);
    setSaved(false);
    setViewing(null);
    setNotes("");
    setClientName(profiles?.find((p) => p.id === selectedId)?.name ?? "");
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/advisor/report/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: selectedId }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => null);
        throw new Error(
          data && typeof data.detail === "string" ? data.detail : `请求失败（HTTP ${res.status}）`
        );
      }

      await readSseStream(res.body, (event) => {
        if (event.type === "token") {
          setText((prev) => prev + String(event.text ?? ""));
        } else if (event.type === "done") {
          setDone(event as unknown as AdvisorDoneEvent);
          if (!event.success) {
            setError(String(event.error_message || "报告校验未通过"));
          }
        } else if (event.type === "error") {
          setError(String(event.message ?? "生成中断"));
        }
      });
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  async function saveReport() {
    if (!done || !text || !clientName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/advisor/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_name: clientName.trim(),
          content: text,
          model: done.model,
          prompt_tokens: done.prompt_tokens,
          completion_tokens: done.completion_tokens,
          notes: notes.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "保存失败");
      setSaved(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function viewReport(reportId: string) {
    setError(null);
    try {
      const res = await fetch(`/api/advisor/reports/${reportId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
      setViewing({ title: `${data.client_name} · ${fmtLocal(data.generated_at)}`, content: data.content });
      setText("");
      setDone(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteReport(reportId: string) {
    setError(null);
    try {
      const res = await fetch(`/api/advisor/reports/${reportId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      }
      setViewing(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const configured = status?.configured ?? false;
  const displayContent = viewing ? viewing.content : text;

  return (
    <div className="flex flex-col gap-6">
      {/* ------------------------------ 配置警告 ------------------------------ */}
      {!configured && (
        <div className="flex items-start gap-3 rounded-xl border border-gold-700/40 bg-gold-500/[0.06] px-4 py-3">
          <Icon name="warning" size={16} className="mt-0.5 shrink-0 text-gold-400" />
          <p className="text-sm leading-6 text-gold-300">
            DEEPSEEK_API_KEY 未配置 —— 请在项目根目录 .env 中设置并重启 API 服务后使用。
          </p>
        </div>
      )}

      {/* ------------------------------ 生成控制 ------------------------------ */}
      <Panel innerClassName="flex flex-col gap-4">
        {profiles === null ? (
          <p className="flex items-center gap-2 text-sm text-cinnabar-300">
            <Icon name="warning" size={15} className="shrink-0" />
            无法获取画像列表 —— 请确认 API 服务已启动。
          </p>
        ) : profiles.length === 0 ? (
          <p className="text-sm leading-6 text-mist-400">
            还没有客户画像。请先在
            <Link
              href="/profiles"
              className="mx-1 text-gold-400 underline decoration-gold-500/40 underline-offset-2 transition-colors hover:text-gold-300"
            >
              客户画像
            </Link>
            页面创建。
          </p>
        ) : (
          <div className="flex flex-wrap items-end gap-4">
            <Field label="选择客户" className="w-full sm:w-72">
              <Select
                value={selectedId ?? ""}
                onChange={(e) => handleSelect(Number(e.target.value))}
                disabled={streaming}
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}（{p.age} 岁{p.risk_level ? ` · ${p.risk_level.split(" / ")[1] ?? p.risk_level}` : ""}）
                  </option>
                ))}
              </Select>
            </Field>

            <Button
              size="lg"
              icon="sparkle"
              onClick={generate}
              disabled={streaming || !configured || selectedId === null}
            >
              {streaming ? "AI 生成中…" : "生成建议书"}
            </Button>

            {streaming && (
              <Button
                variant="ghost"
                size="lg"
                onClick={() => abortRef.current?.abort()}
              >
                停止
              </Button>
            )}

            {status && (
              <span className="pb-1 text-xs text-mist-500 sm:ml-auto">
                模型 <span className="tnum font-mono text-mist-400">{status.model}</span>
              </span>
            )}
          </div>
        )}

        {error && (
          <p className="flex items-center gap-2 text-sm text-cinnabar-300">
            <Icon name="warning" size={14} className="shrink-0" />
            {error}
          </p>
        )}
      </Panel>

      {/* ------------------------------ 报告正文 ------------------------------ */}
      <Panel innerClassName="flex min-h-72 flex-col">
        {displayContent ? (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 font-display text-base text-mist-100">
                <Icon
                  name={viewing ? "scroll" : "sparkle"}
                  size={15}
                  className="text-gold-400"
                />
                {viewing ? viewing.title : "AI 投资建议书"}
              </h3>
              {viewing && (
                <Button variant="ghost" size="sm" icon="x" onClick={() => setViewing(null)}>
                  关闭
                </Button>
              )}
            </div>

            <Markdown>{displayContent}</Markdown>
            {streaming && <span className="animate-blink text-gold-400">▍</span>}

            {done && !viewing && (
              <div className="mt-5 border-t border-white/[0.06] pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="tnum font-mono text-xs text-mist-500">
                    {done.total_tokens.toLocaleString()} tokens（输入{" "}
                    {done.prompt_tokens.toLocaleString()} / 输出{" "}
                    {done.completion_tokens.toLocaleString()}）
                  </p>
                  {saved && (
                    <span className="flex items-center gap-1.5 text-xs text-jade-400">
                      <Icon name="check" size={13} />
                      已保存到报告库
                    </span>
                  )}
                </div>

                {done.success && !saved && (
                  <div className="mt-4">
                    <div className="grid gap-3 sm:grid-cols-[minmax(0,14rem)_1fr]">
                      <Field label="客户名称">
                        <Input
                          value={clientName}
                          onChange={(e) => setClientName(e.target.value)}
                          placeholder="客户名称"
                        />
                      </Field>
                      <Field label="交付备注（可选）">
                        <Textarea
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          rows={2}
                          placeholder="随报告一起存档的一句话备注…"
                        />
                      </Field>
                    </div>
                    <div className="mt-3 flex justify-end">
                      <Button
                        variant="secondary"
                        icon="check"
                        onClick={saveReport}
                        disabled={saving || !clientName.trim()}
                      >
                        {saving ? "保存中…" : "保存到报告库"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <EmptyState
            icon="scroll"
            title={streaming ? "DeepSeek 正在生成…" : "建议书将在此流式呈现"}
            hint={
              streaming
                ? "首段文字即将抵达。"
                : "选择客户后点击「生成建议书」，报告逐字输出，可一键存入报告库。"
            }
            className="flex-1 py-10"
          />
        )}
      </Panel>

      {/* ------------------------------ 历史报告 ------------------------------ */}
      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-xl text-mist-100">报告库</h2>
          <span className="text-[10px] tracking-[0.2em] text-mist-600 uppercase">
            Saved Reports
          </span>
        </div>
        {initialReports.length === 0 ? (
          <Panel>
            <EmptyState
              icon="sparkle"
              title="暂无已保存的报告"
              hint="生成建议书后点击「保存到报告库」，即可在此随时回看。"
            />
          </Panel>
        ) : (
          <Panel pad={false} innerClassName="overflow-hidden">
            <Table className="min-w-[720px]">
              <THead>
                <tr>
                  <TH>客户</TH>
                  <TH>模型</TH>
                  <TH>生成时间</TH>
                  <TH className="text-right">Tokens</TH>
                  <TH className="text-right">操作</TH>
                </tr>
              </THead>
              <tbody>
                {initialReports.map((r) => (
                  <TR key={r.report_id}>
                    <TD>
                      <span className="font-medium text-mist-100">{r.client_name}</span>
                    </TD>
                    <TD>
                      <span className="font-mono text-xs text-mist-500">{r.model}</span>
                    </TD>
                    <TD>
                      <span className="font-mono text-xs text-mist-500">
                        {fmtLocal(r.generated_at)}
                      </span>
                    </TD>
                    <TD className="text-right">
                      <span className="font-mono text-xs">
                        {r.total_tokens.toLocaleString()}
                      </span>
                    </TD>
                    <TD className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="eye"
                          aria-label="查看报告"
                          title="查看"
                          onClick={() => viewReport(r.report_id)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="trash"
                          aria-label="删除报告"
                          title="删除"
                          onClick={() => setPendingDelete(r.report_id)}
                        />
                      </div>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Panel>
        )}
      </section>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这份报告？"
        description="报告将从报告库中永久移除，此操作无法撤销。"
        confirmLabel="删除"
        danger
        onConfirm={() => {
          const id = pendingDelete;
          setPendingDelete(null);
          if (id) void deleteReport(id);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
