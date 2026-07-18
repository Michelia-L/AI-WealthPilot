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
  const [selectedId, setSelectedId] = useState<number | null>(profiles?.[0]?.id ?? null);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState("");
  const [done, setDone] = useState<AdvisorDoneEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [viewing, setViewing] = useState<{ title: string; content: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const selectedProfile = profiles?.find((p) => p.id === selectedId) ?? null;

  async function generate() {
    if (selectedId === null) return;
    setStreaming(true);
    setText("");
    setDone(null);
    setError(null);
    setSaved(false);
    setViewing(null);
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
    if (!done || !selectedProfile || !text) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/advisor/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_name: selectedProfile.name,
          content: text,
          model: done.model,
          prompt_tokens: done.prompt_tokens,
          completion_tokens: done.completion_tokens,
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
    if (!window.confirm("确定删除这份报告？")) return;
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
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 生成控制 ------------------------------ */}
      <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        {!configured && (
          <div className="rounded-lg border border-amber-800/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
            ⚠ DEEPSEEK_API_KEY 未配置 —— 请在项目根目录 .env 中设置并重启 API 服务后使用。
          </div>
        )}

        {profiles === null ? (
          <p className="text-sm text-rose-400">无法获取画像列表 —— 请确认 API 服务已启动。</p>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-slate-400">
            还没有客户画像。请先在
            <Link href="/profiles" className="mx-1 text-amber-400 underline hover:text-amber-300">
              客户画像
            </Link>
            页面创建。
          </p>
        ) : (
          <div className="flex flex-wrap items-end gap-4">
            <label className="block text-sm text-slate-300">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                选择画像
              </span>
              <select
                value={selectedId ?? ""}
                onChange={(e) => setSelectedId(Number(e.target.value))}
                disabled={streaming}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}（{p.age} 岁{p.risk_level ? ` · ${p.risk_level.split(" / ")[1] ?? p.risk_level}` : ""}）
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={generate}
              disabled={streaming || !configured || selectedId === null}
              className="rounded-lg bg-amber-500 px-6 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {streaming ? "AI 生成中…" : "🧠 生成建议书"}
            </button>

            {streaming && (
              <button
                type="button"
                onClick={() => abortRef.current?.abort()}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                中止
              </button>
            )}

            {status && (
              <span className="text-xs text-slate-600">模型：{status.model}</span>
            )}
          </div>
        )}

        {error && <p className="text-sm text-rose-400">⚠ {error}</p>}
      </div>

      {/* ------------------------------ 报告正文 ------------------------------ */}
      {displayContent && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">
              {viewing ? `📄 ${viewing.title}` : "📝 AI 投资建议书"}
              {streaming && <span className="ml-2 animate-pulse text-amber-400">▍</span>}
            </h3>
            <div className="flex items-center gap-3">
              {done && !viewing && (
                <span className="text-xs text-slate-500">
                  {done.total_tokens.toLocaleString()} tokens
                  （输入 {done.prompt_tokens.toLocaleString()} / 输出 {done.completion_tokens.toLocaleString()}）
                </span>
              )}
              {done?.success && !viewing && !saved && (
                <button
                  type="button"
                  onClick={saveReport}
                  disabled={saving}
                  className="rounded-lg border border-amber-700/60 bg-amber-500/10 px-4 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-500/20 disabled:opacity-40"
                >
                  {saving ? "保存中…" : "💾 保存到报告库"}
                </button>
              )}
              {saved && <span className="text-xs text-emerald-400">✓ 已保存</span>}
              {viewing && (
                <button
                  type="button"
                  onClick={() => setViewing(null)}
                  className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
                >
                  关闭
                </button>
              )}
            </div>
          </div>
          <Markdown>{displayContent}</Markdown>
        </div>
      )}

      {/* ------------------------------ 历史报告 ------------------------------ */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-200">
          报告库 <span className="font-normal text-slate-500">— 已保存的建议书</span>
        </h3>
        {initialReports.length === 0 ? (
          <p className="text-sm text-slate-500">暂无已保存的报告。</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">客户</th>
                  <th className="px-4 py-3 font-medium">生成时间</th>
                  <th className="px-4 py-3 text-right font-medium">Tokens</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                {initialReports.map((r) => (
                  <tr key={r.report_id} className="text-slate-300">
                    <td className="px-4 py-3 font-medium text-slate-100">{r.client_name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {fmtLocal(r.generated_at)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {r.total_tokens.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => viewReport(r.report_id)}
                        className="mr-2 rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
                      >
                        查看
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteReport(r.report_id)}
                        className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-500 hover:text-rose-300"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
