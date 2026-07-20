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
import { readSseStream } from "@/lib/sse";
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
        typeof data.detail === "string"
          ? data.detail
          : `创建任务失败（HTTP ${res.status}）`
      );
    }

    const eventsRes = await fetch(`/api/portfolio/tasks/${data.task_id}/events`);
    if (!eventsRes.ok || !eventsRes.body) {
      const err = await eventsRes.json().catch(() => null);
      throw new Error(
        err && typeof err.detail === "string" ? err.detail : "无法接收任务进度"
      );
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
    if (!finalResult)
      throw new Error("任务流意外结束（服务可能已重启，请重试）");
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
            typeof data.detail === "string"
              ? data.detail
              : `请求失败（HTTP ${res.status}）`
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
