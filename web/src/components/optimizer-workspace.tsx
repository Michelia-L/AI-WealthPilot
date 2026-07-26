"use client";

import { useEffect, useRef, useState } from "react";
import type {
  AssetClassInfo,
  BLViewInput,
  OptimizeMethod,
  OptimizeMode,
  OptimizeRequest,
  OptimizeResponse,
} from "@/lib/api";
import { OPTIMIZER_PERIOD_OPTIONS } from "@/lib/api";
import { readSseStream } from "@/lib/sse";
import {
  TaskGoneError,
  clearActiveTask,
  loadActiveTask,
  saveActiveTask,
} from "@/lib/task-resume";
import { useClient } from "./client-context";
import Button from "./ui/button";
import Icon from "./ui/icon";
import Panel from "./ui/panel";
import { Chip } from "./ui/chip";
import Segmented from "./ui/segmented";
import Toggle from "./ui/toggle";
import Slider from "./ui/slider";
import { NumInput } from "./ui/field";
import EmptyState from "./ui/empty";
import Group from "./optimizer/group";
import BLConfigPanel from "./optimizer/bl-config-panel";
import OptimizerResults from "./optimizer/optimizer-results";

const DEFAULT_ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"];

const METHOD_OPTIONS: { value: OptimizeMethod; label: string }[] = [
  { value: "mvo", label: "传统 MVO" },
  { value: "resampled", label: "重采样 MVO" },
  { value: "black-litterman", label: "Black-Litterman" },
];

const MODE_OPTIONS: { value: OptimizeMode; label: string }[] = [
  { value: "max-sharpe", label: "最大夏普" },
  { value: "min-vol", label: "最小波动" },
];

export default function OptimizerWorkspace({
  assetClasses,
  initialAssets,
}: {
  assetClasses: Record<string, AssetClassInfo>;
  /** URL 深链（如监控页 SAA 联动）预填的资产选择。 */
  initialAssets?: string[];
}) {
  const allKeys = Object.keys(assetClasses);

  const [assets, setAssets] = useState<string[]>(
    initialAssets && initialAssets.length >= 2 ? initialAssets : DEFAULT_ASSETS
  );
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
  const [marketWeights, setMarketWeights] = useState<Record<string, string>>(
    {}
  );
  const [views, setViews] = useState<BLViewInput[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);

  // 全局客户上下文：选中客户后可把其风险等级注入为权重约束
  const { clientId, clientName } = useClient();
  const [applyRisk, setApplyRisk] = useState(true);

  function toggleAsset(key: string) {
    setAssets((prev) => {
      if (prev.includes(key)) {
        if (prev.length <= 2) return prev; // API requires >= 2
        return prev.filter((k) => k !== key);
      }
      return [...prev, key];
    });
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
    if (method === "mvo" && applyRisk && clientId !== null) {
      body.profile_id = clientId;
    }
    return body;
  }

  // 当前事件流的取消句柄：切页卸载时断开（服务端任务独立运行，重挂载后凭
  // sessionStorage 里的 task_id 重连，后端会从持久化事件完整回放）。
  const streamAbort = useRef<AbortController | null>(null);

  /** Open the task event stream and pump it; resolves with the final result. */
  async function streamTaskEvents(
    taskId: string,
    signal: AbortSignal,
    onOpen?: () => void
  ): Promise<OptimizeResponse> {
    const eventsRes = await fetch(`/api/portfolio/tasks/${taskId}/events`, {
      signal,
    });
    if (!eventsRes.ok || !eventsRes.body) {
      if (eventsRes.status === 404) {
        clearActiveTask("portfolio");
        throw new TaskGoneError();
      }
      const err = await eventsRes.json().catch(() => null);
      throw new Error(
        err && typeof err.detail === "string" ? err.detail : "无法接收任务进度"
      );
    }
    onOpen?.();
    let finalResult: OptimizeResponse | null = null;
    let streamError: string | null = null;
    await readSseStream(eventsRes.body, (event) => {
      if (event.type === "node") {
        setProgressLabel(String(event.label ?? ""));
      } else if (event.type === "done") {
        finalResult = event.result as OptimizeResponse;
        clearActiveTask("portfolio");
      } else if (event.type === "error") {
        streamError = String(event.message ?? "优化失败");
        clearActiveTask("portfolio");
      }
    });
    if (streamError) throw new Error(streamError);
    if (!finalResult)
      throw new Error("任务流意外结束（服务可能已重启，请重试）");
    return finalResult;
  }

  // 挂载时恢复未完成的任务（切页返回的场景）：重连事件流重建进度与结果。
  useEffect(() => {
    const taskId = loadActiveTask("portfolio");
    if (!taskId) return;
    const controller = new AbortController();
    streamAbort.current = controller;
    void (async () => {
      try {
        const result = await streamTaskEvents(taskId, controller.signal, () => {
          // fetch 返回后的异步边界里再 setState，避免 effect 内同步 setState
          setLoading(true);
          setError(null);
          setProgressLabel(null);
        });
        setResult(result);
      } catch (e) {
        if (e instanceof TaskGoneError || controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setProgressLabel(null);
        }
      }
    })();
    return () => controller.abort();
  }, []);

  // 卸载时断开事件流（任务在服务端继续，句柄保留供重连）
  useEffect(() => () => streamAbort.current?.abort(), []);

  /** Resampled MVO path: async task + SSE progress (minute-level compute). */
  async function runAsync(
    body: OptimizeRequest,
    signal: AbortSignal
  ): Promise<OptimizeResponse> {
    const res = await fetch("/api/portfolio/optimize/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : `创建任务失败（HTTP ${res.status}）`
      );
    }
    saveActiveTask("portfolio", String(data.task_id));
    return streamTaskEvents(String(data.task_id), signal);
  }

  async function run() {
    const controller = new AbortController();
    streamAbort.current?.abort();
    streamAbort.current = controller;
    setLoading(true);
    setError(null);
    setProgressLabel(null);
    try {
      const body = buildBody();
      if (method === "resampled") {
        setResult(await runAsync(body, controller.signal));
      } else {
        const res = await fetch("/api/portfolio/optimize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : `请求失败（HTTP ${res.status}）`
          );
        }
        setResult(data as OptimizeResponse);
      }
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setProgressLabel(null);
      }
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 参数表单 ------------------------------ */}
      <Panel innerClassName="space-y-6">
        <Group label={`资产类别 · 已选 ${assets.length}（至少 2 个）`}>
          <div className="flex flex-wrap gap-2">
            {allKeys.map((k) => (
              <Chip
                key={k}
                selected={assets.includes(k)}
                onClick={() => toggleAsset(k)}
              >
                {assetClasses[k].name}
              </Chip>
            ))}
          </div>
        </Group>

        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          <Group label="历史窗口">
            <Segmented
              size="sm"
              options={OPTIMIZER_PERIOD_OPTIONS}
              value={period}
              onChange={setPeriod}
            />
          </Group>

          <Group label="优化方法">
            <Segmented
              size="sm"
              options={METHOD_OPTIONS}
              value={method}
              onChange={setMethod}
            />
          </Group>

          <Group label="目标">
            <Segmented
              size="sm"
              options={MODE_OPTIONS}
              value={mode}
              onChange={setMode}
            />
          </Group>

          <Group label="无风险利率">
            <div className="flex items-center gap-3 pt-0.5">
              <Toggle checked={rfAuto} onChange={setRfAuto} label="自动获取" />
              {!rfAuto && (
                <span className="flex items-center gap-1.5 text-sm text-mist-300">
                  <NumInput
                    aria-label="手动无风险利率（%）"
                    step="0.1"
                    min="0"
                    max="20"
                    value={rfManual}
                    onChange={(e) => setRfManual(e.target.value)}
                    className="w-20 px-2 py-1 text-xs"
                  />
                  %
                </span>
              )}
            </div>
          </Group>
        </div>

        <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
          <Toggle
            checked={allowShort}
            onChange={setAllowShort}
            label="允许做空"
          />
          {method === "resampled" && (
            <Slider
              label="模拟次数"
              value={nSim}
              min={50}
              max={1000}
              step={50}
              onChange={setNSim}
              className="w-56"
            />
          )}
          {clientId !== null ? (
            <span className="flex items-center gap-2.5">
              <span
                className={
                  method !== "mvo" ? "pointer-events-none opacity-50" : ""
                }
              >
                <Toggle
                  checked={applyRisk}
                  onChange={setApplyRisk}
                  label={`客户风险约束（${clientName}）`}
                />
              </span>
              {method !== "mvo" && (
                <span className="text-[11px] text-mist-600">
                  仅传统 MVO 生效
                </span>
              )}
            </span>
          ) : (
            <span className="text-[11px] text-mist-600">
              在侧边栏选择客户后，可将其风险等级注入为权重约束
            </span>
          )}
        </div>

        {/* --------------------------- BL 配置面板 --------------------------- */}
        {method === "black-litterman" && (
          <BLConfigPanel
            assets={assets}
            assetClasses={assetClasses}
            blTau={blTau}
            setBlTau={setBlTau}
            blDelta={blDelta}
            setBlDelta={setBlDelta}
            equalWeights={equalWeights}
            setEqualWeights={setEqualWeights}
            marketWeights={marketWeights}
            setMarketWeights={setMarketWeights}
            views={views}
            setViews={setViews}
          />
        )}

        <div className="flex flex-wrap items-center gap-4 border-t border-white/[0.05] pt-5">
          <Button
            variant="primary"
            size="lg"
            trailingIcon="arrowRight"
            onClick={run}
            disabled={
              loading ||
              assets.length < 2 ||
              (method === "black-litterman" && views.length === 0)
            }
          >
            {loading ? "优化计算中…" : "运行优化"}
          </Button>
          {loading && (
            <span className="flex items-center gap-2 text-xs text-mist-500">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold-400" />
              {progressLabel ??
                (method === "resampled"
                  ? "重采样任务已创建，等待进度…"
                  : "正在获取行情并求解…")}
            </span>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2.5 rounded-xl border border-cinnabar-500/25 bg-cinnabar-500/[0.08] px-4 py-3 text-sm text-cinnabar-300">
            <Icon
              name="warning"
              size={15}
              className="mt-0.5 text-cinnabar-400"
            />
            <span>{error}</span>
          </div>
        )}
      </Panel>

      {/* ------------------------------ 结果区 ------------------------------ */}
      {result ? (
        <OptimizerResults result={result} />
      ) : (
        <Panel pad={false}>
          <EmptyState
            icon="pie"
            title="配置参数并开始优化"
            hint="至少选择 2 个资产类别；提交后将展示有效前沿、配置权重与关键指标。"
          />
        </Panel>
      )}
    </div>
  );
}
