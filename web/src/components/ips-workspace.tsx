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
  const [selectedId, setSelectedId] = useState<number | null>(profiles?.[0]?.id ?? null);
  const [maxRevisions, setMaxRevisions] = useState(3);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [doneInfo, setDoneInfo] = useState<DoneInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{
    documentId: string;
    title: string;
    markdown: string;
  } | null>(null);

  const configured = status?.configured ?? false;

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
        markdown: data.markdown,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

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
                disabled={running}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}（{p.age} 岁{p.risk_level ? ` · ${p.risk_level.split(" / ")[1] ?? p.risk_level}` : ""}）
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm text-slate-300">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                最大修订轮数
              </span>
              <div className="flex overflow-hidden rounded-lg border border-slate-700">
                {MAX_REVISION_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setMaxRevisions(n)}
                    disabled={running}
                    className={`px-3 py-2 text-xs font-medium transition-colors ${
                      maxRevisions === n
                        ? "bg-slate-700 text-slate-100"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </label>

            <button
              type="button"
              onClick={generate}
              disabled={running || !configured || selectedId === null}
              className="rounded-lg bg-amber-500 px-6 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? "工作流运行中…" : "📜 生成 IPS"}
            </button>

            <span className="text-xs text-slate-600">
              多智能体工作流：CME → 初稿 → 三维评审 → SAA 量化验证 → 修订/定稿（通常需要数分钟）
            </span>
          </div>
        )}

        {error && <p className="text-sm text-rose-400">⚠ {error}</p>}
      </div>

      {/* ------------------------------ 进度时间线 ------------------------------ */}
      {(steps.length > 0 || running) && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-200">工作流进度</h3>
          <ol className="space-y-2.5">
            {steps.map((s, i) => (
              <li key={`${s.node}-${i}`} className="flex items-center gap-3 text-sm">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-900/60 text-xs text-emerald-300">
                  ✓
                </span>
                <span className="text-slate-300">{s.label}</span>
              </li>
            ))}
            {running && (
              <li className="flex items-center gap-3 text-sm">
                <span className="flex h-5 w-5 items-center justify-center">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
                </span>
                <span className="animate-pulse text-amber-300">正在处理…</span>
              </li>
            )}
          </ol>

          {doneInfo && (
            <div className="mt-4 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
              ✓ IPS 已生成并入库（状态：{doneInfo.status}
              {doneInfo.revision_count > 0 ? `，修订 ${doneInfo.revision_count} 轮` : ""}）
              <button
                type="button"
                onClick={() =>
                  viewDocument({
                    document_id: doneInfo.document_id,
                    client_name: "",
                    version: "?",
                    risk_level: "",
                    status: "",
                    revision_rounds: 0,
                    saved_at: "",
                  })
                }
                className="ml-3 underline hover:text-emerald-200"
              >
                立即查看 →
              </button>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------ 文档查看 ------------------------------ */}
      {viewing && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">📄 {viewing.title}</h3>
            <div className="flex items-center gap-2">
              <a
                href={`/api/ips/${encodeURIComponent(viewing.documentId)}/pdf`}
                className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-amber-300"
              >
                ⬇ 下载 PDF
              </a>
              <button
                type="button"
                onClick={() => setViewing(null)}
                className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
              >
                关闭
              </button>
            </div>
          </div>
          <Markdown>{viewing.markdown}</Markdown>
        </div>
      )}

      {/* ------------------------------ 文档库 ------------------------------ */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-200">
          IPS 文档库 <span className="font-normal text-slate-500">— 与 Streamlit 共享存储</span>
        </h3>
        {initialDocuments.length === 0 ? (
          <p className="text-sm text-slate-500">暂无 IPS 文档。</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">客户</th>
                  <th className="px-4 py-3 font-medium">版本</th>
                  <th className="px-4 py-3 font-medium">风险等级</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 text-right font-medium">修订轮数</th>
                  <th className="px-4 py-3 font-medium">保存时间</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                {initialDocuments.map((d) => (
                  <tr key={d.document_id} className="text-slate-300">
                    <td className="px-4 py-3 font-medium text-slate-100">{d.client_name}</td>
                    <td className="px-4 py-3 font-mono text-xs">{d.version}</td>
                    <td className="px-4 py-3 text-xs">{d.risk_level}</td>
                    <td className="px-4 py-3 text-xs">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 font-medium ${
                          d.status === "approved"
                            ? "bg-emerald-900/60 text-emerald-300"
                            : "bg-amber-900/60 text-amber-300"
                        }`}
                      >
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">{d.revision_rounds}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {fmtLocal(d.saved_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => viewDocument(d)}
                        className="mr-2 rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
                      >
                        查看
                      </button>
                      <a
                        href={`/api/ips/${encodeURIComponent(d.document_id)}/pdf`}
                        className="inline-block rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-amber-300"
                      >
                        ⬇ PDF
                      </a>
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
