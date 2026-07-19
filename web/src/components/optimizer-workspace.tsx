"use client";

import { useState } from "react";
import type {
  AssetClassInfo,
  BLViewInput,
  OptimizeMethod,
  OptimizeMode,
  OptimizeRequest,
  OptimizeResponse,
} from "@/lib/api";
import { OPTIMIZER_PERIOD_OPTIONS } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { readSseStream } from "@/lib/sse";
import PlotChart from "@/components/plot-chart";

const DEFAULT_ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"];

const METHOD_OPTIONS: { value: OptimizeMethod; label: string; hint: string }[] = [
  { value: "mvo", label: "传统 MVO", hint: "均值-方差（SLSQP）" },
  { value: "resampled", label: "重采样 MVO", hint: "Michaud 方法" },
  { value: "black-litterman", label: "Black-Litterman", hint: "贝叶斯观点融合" },
];

function Chip({
  active,
  onClick,
  children,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
          : "border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      {children}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition-colors ${
          checked ? "bg-amber-500" : "bg-slate-700"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
            checked ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </button>
      {label}
    </label>
  );
}

export default function OptimizerWorkspace({
  assetClasses,
}: {
  assetClasses: Record<string, AssetClassInfo>;
}) {
  const allKeys = Object.keys(assetClasses);

  const [assets, setAssets] = useState<string[]>(DEFAULT_ASSETS);
  const [period, setPeriod] = useState("5y");
  const [method, setMethod] = useState<OptimizeMethod>("mvo");
  const [mode, setMode] = useState<OptimizeMode>("max-sharpe");
  const [allowShort, setAllowShort] = useState(false);
  const [rfAuto, setRfAuto] = useState(true);
  const [rfManual, setRfManual] = useState("4.5");
  const [nSim, setNSim] = useState(200);

  const [blTau, setBlTau] = useState("0.025");
  const [blDelta, setBlDelta] = useState("2.5");
  const [equalWeights, setEqualWeights] = useState(true);
  const [marketWeights, setMarketWeights] = useState<Record<string, string>>({});
  const [views, setViews] = useState<BLViewInput[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);

  function toggleAsset(key: string) {
    setAssets((prev) => {
      if (prev.includes(key)) {
        if (prev.length <= 2) return prev; // API requires >= 2
        return prev.filter((k) => k !== key);
      }
      return [...prev, key];
    });
  }

  function addView() {
    setViews((prev) => [
      ...prev,
      {
        view_type: "absolute",
        asset_long: assets[0],
        asset_short: null,
        expected_return: 0.1,
        confidence: 70,
      },
    ]);
  }

  function updateView(i: number, patch: Partial<BLViewInput>) {
    setViews((prev) => prev.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  }

  function buildBody(): OptimizeRequest {
    const body: OptimizeRequest = {
      assets,
      period,
      method,
      mode,
      allow_short: allowShort,
      n_simulations: nSim,
      risk_free_rate: rfAuto ? null : parseFloat(rfManual || "0") / 100,
    };
    if (method === "black-litterman") {
      body.bl = {
        tau: parseFloat(blTau) || 0.025,
        delta: parseFloat(blDelta) || 2.5,
        market_weights: equalWeights
          ? null
          : Object.fromEntries(
              assets.map((k) => [
                k,
                (parseFloat(marketWeights[k] ?? "0") || 0) / 100,
              ])
            ),
        views,
      };
    }
    return body;
  }

  /** Resampled MVO path: async task + SSE progress (minute-level compute). */
  async function runAsync(body: OptimizeRequest): Promise<OptimizeResponse> {
    const res = await fetch("/api/portfolio/optimize/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(
        typeof data.detail === "string" ? data.detail : `创建任务失败（HTTP ${res.status}）`
      );
    }

    const eventsRes = await fetch(`/api/portfolio/tasks/${data.task_id}/events`);
    if (!eventsRes.ok || !eventsRes.body) {
      const err = await eventsRes.json().catch(() => null);
      throw new Error(err && typeof err.detail === "string" ? err.detail : "无法接收任务进度");
    }
    let finalResult: OptimizeResponse | null = null;
    let streamError: string | null = null;
    await readSseStream(eventsRes.body, (event) => {
      if (event.type === "node") {
        setProgressLabel(String(event.label ?? ""));
      } else if (event.type === "done") {
        finalResult = event.result as OptimizeResponse;
      } else if (event.type === "error") {
        streamError = String(event.message ?? "优化失败");
      }
    });
    if (streamError) throw new Error(streamError);
    if (!finalResult) throw new Error("任务流意外结束（服务可能已重启，请重试）");
    return finalResult;
  }

  async function run() {
    setLoading(true);
    setError(null);
    setProgressLabel(null);
    try {
      const body = buildBody();
      if (method === "resampled") {
        setResult(await runAsync(body));
      } else {
        const res = await fetch("/api/portfolio/optimize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(
            typeof data.detail === "string" ? data.detail : `请求失败（HTTP ${res.status}）`
          );
        }
        setResult(data as OptimizeResponse);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
      setProgressLabel(null);
    }
  }

  const selectedWeightOf = (name: string) => result?.selected.weights[name] ?? 0;

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 参数表单 ------------------------------ */}
      <div className="space-y-5 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <Field label={`资产类别（${assets.length} 已选，至少 2 个）`}>
          <div className="flex flex-wrap gap-2">
            {allKeys.map((k) => (
              <Chip key={k} active={assets.includes(k)} onClick={() => toggleAsset(k)}>
                {assetClasses[k].name}
              </Chip>
            ))}
          </div>
        </Field>

        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          <Field label="历史窗口">
            <div className="flex flex-wrap gap-1.5">
              {OPTIMIZER_PERIOD_OPTIONS.map((p) => (
                <Chip key={p.value} active={period === p.value} onClick={() => setPeriod(p.value)}>
                  {p.label}
                </Chip>
              ))}
            </div>
          </Field>

          <Field label="优化方法">
            <div className="flex flex-wrap gap-1.5">
              {METHOD_OPTIONS.map((m) => (
                <Chip key={m.value} active={method === m.value} onClick={() => setMethod(m.value)}>
                  {m.label}
                </Chip>
              ))}
            </div>
          </Field>

          <Field label="目标">
            <div className="flex flex-wrap gap-1.5">
              <Chip active={mode === "max-sharpe"} onClick={() => setMode("max-sharpe")}>
                最大夏普
              </Chip>
              <Chip active={mode === "min-vol"} onClick={() => setMode("min-vol")}>
                最小波动
              </Chip>
            </div>
          </Field>

          <Field label="无风险利率">
            <div className="flex items-center gap-3">
              <Toggle checked={rfAuto} onChange={setRfAuto} label="自动获取" />
              {!rfAuto && (
                <span className="flex items-center gap-1 text-sm text-slate-300">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="20"
                    value={rfManual}
                    onChange={(e) => setRfManual(e.target.value)}
                    className="w-20 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-sm text-slate-100"
                  />
                  %
                </span>
              )}
            </div>
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <Toggle checked={allowShort} onChange={setAllowShort} label="允许做空" />
          {method === "resampled" && (
            <label className="flex items-center gap-3 text-sm text-slate-300">
              模拟次数
              <input
                type="range"
                min={50}
                max={1000}
                step={50}
                value={nSim}
                onChange={(e) => setNSim(parseInt(e.target.value))}
                className="w-40 accent-amber-500"
              />
              <span className="w-12 font-mono text-slate-100">{nSim}</span>
            </label>
          )}
        </div>

        {/* --------------------------- BL 配置面板 --------------------------- */}
        {method === "black-litterman" && (
          <div className="space-y-4 rounded-lg border border-slate-700/60 bg-slate-950/40 p-4">
            <div className="grid gap-4 md:grid-cols-3">
              <Field label="τ（不确定性缩放）">
                <input
                  type="number"
                  step="0.005"
                  min="0.01"
                  max="0.1"
                  value={blTau}
                  onChange={(e) => setBlTau(e.target.value)}
                  className="w-24 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-sm text-slate-100"
                />
              </Field>
              <Field label="δ（风险厌恶系数）">
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="10"
                  value={blDelta}
                  onChange={(e) => setBlDelta(e.target.value)}
                  className="w-24 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-sm text-slate-100"
                />
              </Field>
              <Field label="市值权重">
                <Toggle
                  checked={equalWeights}
                  onChange={setEqualWeights}
                  label={equalWeights ? "等权（1/N）" : "自定义"}
                />
              </Field>
            </div>

            {!equalWeights && (
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {assets.map((k) => (
                  <label key={k} className="flex items-center gap-2 text-xs text-slate-400">
                    <span className="w-28 truncate">{assetClasses[k].name}</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      placeholder={(100 / assets.length).toFixed(0)}
                      value={marketWeights[k] ?? ""}
                      onChange={(e) =>
                        setMarketWeights((prev) => ({ ...prev, [k]: e.target.value }))
                      }
                      className="w-16 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
                    />
                    %
                  </label>
                ))}
              </div>
            )}

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  投资者观点（{views.length}）
                </span>
                <button
                  type="button"
                  onClick={addView}
                  className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/20"
                >
                  + 添加观点
                </button>
              </div>

              {views.length === 0 && (
                <p className="text-xs text-slate-500">
                  Black-Litterman 需要至少一条观点。绝对观点：看多某资产至目标收益；相对观点：A
                  相对 B 的超额收益。
                </p>
              )}

              <div className="space-y-2">
                {views.map((v, i) => (
                  <div
                    key={i}
                    className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-sm"
                  >
                    <select
                      value={v.view_type}
                      onChange={(e) =>
                        updateView(i, { view_type: e.target.value as "absolute" | "relative" })
                      }
                      className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                    >
                      <option value="absolute">绝对</option>
                      <option value="relative">相对</option>
                    </select>

                    <select
                      value={v.asset_long}
                      onChange={(e) => updateView(i, { asset_long: e.target.value })}
                      className="max-w-44 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                    >
                      {assets.map((k) => (
                        <option key={k} value={k}>
                          {assetClasses[k].name}
                        </option>
                      ))}
                    </select>

                    {v.view_type === "relative" && (
                      <>
                        <span className="text-slate-500">跑赢</span>
                        <select
                          value={v.asset_short ?? ""}
                          onChange={(e) => updateView(i, { asset_short: e.target.value })}
                          className="max-w-44 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                        >
                          {assets
                            .filter((k) => k !== v.asset_long)
                            .map((k) => (
                              <option key={k} value={k}>
                                {assetClasses[k].name}
                              </option>
                            ))}
                        </select>
                      </>
                    )}

                    <span className="flex items-center gap-1 text-slate-400">
                      {v.view_type === "absolute" ? "预期收益" : "超额"}
                      <input
                        type="number"
                        step="1"
                        value={Math.round(v.expected_return * 100)}
                        onChange={(e) =>
                          updateView(i, {
                            expected_return: (parseFloat(e.target.value) || 0) / 100,
                          })
                        }
                        className="w-16 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-slate-100"
                      />
                      %
                    </span>

                    <span className="flex items-center gap-2 text-xs text-slate-400">
                      置信度
                      <input
                        type="range"
                        min={10}
                        max={100}
                        step={5}
                        value={v.confidence}
                        onChange={(e) =>
                          updateView(i, { confidence: parseInt(e.target.value) })
                        }
                        className="w-24 accent-amber-500"
                      />
                      <span className="w-10 font-mono text-slate-200">{v.confidence}%</span>
                    </span>

                    <button
                      type="button"
                      onClick={() => setViews((prev) => prev.filter((_, j) => j !== i))}
                      className="ml-auto text-slate-500 hover:text-rose-400"
                      aria-label="删除观点"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-4 pt-1">
          <button
            type="button"
            onClick={run}
            disabled={loading || assets.length < 2 || (method === "black-litterman" && views.length === 0)}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "优化计算中…" : "运行优化"}
          </button>
          {loading && (
            <span className="text-xs text-slate-500">
              {progressLabel ??
                (method === "resampled"
                  ? "重采样任务已创建，等待进度…"
                  : "正在获取行情并求解…")}
            </span>
          )}
          {error && <span className="text-sm text-rose-400">⚠ {error}</span>}
        </div>
      </div>

      {/* ------------------------------ 结果区 ------------------------------ */}
      {result && (
        <>
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "年化收益", value: fmtPct(result.selected.ann_return), tone: "text-emerald-400" },
              { label: "年化波动", value: fmtPct(result.selected.ann_volatility), tone: "text-amber-300" },
              { label: "夏普比率", value: result.selected.sharpe.toFixed(2), tone: "text-sky-400" },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="text-xs text-slate-500">{m.label}</div>
                <div className={`mt-1 font-mono text-2xl font-semibold ${m.tone}`}>{m.value}</div>
              </div>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
              <PlotChart figure={result.frontier_chart} height={480} />
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
              <PlotChart figure={result.allocation_chart} height={480} />
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">资产</th>
                  <th className="px-4 py-3 text-right font-medium">配置权重</th>
                  {result.selected.weight_std && (
                    <th className="px-4 py-3 text-right font-medium">权重波动 σ</th>
                  )}
                  <th className="px-4 py-3 text-right font-medium">年化收益</th>
                  <th className="px-4 py-3 text-right font-medium">年化波动</th>
                  {result.bl && (
                    <>
                      <th className="px-4 py-3 text-right font-medium">均衡收益</th>
                      <th className="px-4 py-3 text-right font-medium">后验收益</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                {[...result.asset_stats]
                  .sort((a, b) => Math.abs(selectedWeightOf(b.name)) - Math.abs(selectedWeightOf(a.name)))
                  .map((s) => {
                    const w = selectedWeightOf(s.name);
                    return (
                      <tr key={s.key} className="text-slate-300">
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-100">{s.name}</div>
                          <div className="font-mono text-xs text-slate-500">{s.ticker}</div>
                        </td>
                        <td
                          className={`px-4 py-3 text-right font-mono ${
                            w < -0.0005 ? "text-rose-400" : w > 0.0005 ? "text-emerald-400" : "text-slate-600"
                          }`}
                        >
                          {fmtPct(w, 1)}
                        </td>
                        {result.selected.weight_std && (
                          <td className="px-4 py-3 text-right font-mono text-slate-400">
                            {fmtPct(result.selected.weight_std[s.name] ?? null, 1)}
                          </td>
                        )}
                        <td className="px-4 py-3 text-right font-mono">{fmtPct(s.ann_return)}</td>
                        <td className="px-4 py-3 text-right font-mono">{fmtPct(s.ann_volatility)}</td>
                        {result.bl && (
                          <>
                            <td className="px-4 py-3 text-right font-mono text-slate-400">
                              {fmtPct(result.bl.equilibrium_returns[s.name] ?? null)}
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-amber-300">
                              {fmtPct(result.bl.posterior_returns[s.name] ?? null)}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {(
              [
                ["当前选中", result.selected],
                ["最大夏普", result.max_sharpe],
                ["最小波动", result.min_vol],
              ] as const
            ).map(([label, r]) => (
              <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm">
                <div className="mb-2 font-medium text-slate-200">{label}</div>
                <div className="grid grid-cols-3 gap-2 font-mono text-xs text-slate-400">
                  <span>
                    收益
                    <div className="text-sm text-slate-200">{fmtPct(r.ann_return)}</div>
                  </span>
                  <span>
                    波动
                    <div className="text-sm text-slate-200">{fmtPct(r.ann_volatility)}</div>
                  </span>
                  <span>
                    夏普
                    <div className="text-sm text-slate-200">{r.sharpe.toFixed(2)}</div>
                  </span>
                </div>
              </div>
            ))}
          </div>

          <p className="text-xs text-slate-600">
            参数：{result.params.period} 窗口 · {result.params.trading_days} 个交易日 · 无风险利率{" "}
            {fmtPct(result.params.risk_free_rate)} · {result.params.allow_short ? "允许做空" : "仅多头"}
            {result.params.n_simulations ? ` · ${result.params.n_simulations} 次重采样` : ""}
          </p>
        </>
      )}
    </div>
  );
}
