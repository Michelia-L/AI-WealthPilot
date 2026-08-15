"use client";

import type {
  AssetClassInfo,
  OptimizeMethod,
  OptimizeMode,
} from "@/lib/api";
import { OPTIMIZER_PERIOD_OPTIONS } from "@/lib/api";
import type { OptimizerDeepLink } from "@/lib/optimizer-link";
import { useClient } from "./client-context";
import { useT } from "@/components/locale-context";
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
import SurplusConfigPanel from "./optimizer/surplus-config-panel";
import OptimizerResults from "./optimizer/optimizer-results";
import { useOptimizerForm } from "./optimizer/use-optimizer-form";
import { useOptimizeRun } from "./optimizer/use-optimize-run";

const CVAR_CONFIDENCE_OPTIONS = [
  { value: 0.9, label: "90%" },
  { value: 0.95, label: "95%" },
  { value: 0.99, label: "99%" },
] as const;

export default function OptimizerWorkspace({
  assetClasses,
  initialAssets,
  deepLink,
}: {
  assetClasses: Record<string, AssetClassInfo>;
  /** URL 深链（如监控页 SAA 联动）预填的资产选择。 */
  initialAssets?: string[];
  /** URL 深链（退休页 LDI 联动）预填的方法与盈余通道参数。 */
  deepLink?: OptimizerDeepLink;
}) {
  const t = useT();
  const allKeys = Object.keys(assetClasses);
  // 全局客户上下文：选中客户后可把其风险等级注入为权重约束
  const { clientId, clientName } = useClient();

  const form = useOptimizerForm({ initialAssets, deepLink });
  const { loading, error, result, progressLabel, run } = useOptimizeRun({
    buildBody: form.buildBody,
    method: form.method,
  });
  const {
    assets,
    toggleAsset,
    period,
    setPeriod,
    method,
    setMethod,
    mode,
    setMode,
    allowShort,
    setAllowShort,
    rfAuto,
    setRfAuto,
    rfManual,
    setRfManual,
    nSim,
    setNSim,
    cvarConf,
    setCvarConf,
    erSource,
    setErSource,
    surplusSource,
    setSurplusSource,
    liabRatio,
    setLiabRatio,
    liabDuration,
    setLiabDuration,
    surplusProxy,
    setSurplusProxy,
    growthSource,
    setGrowthSource,
    customGrowth,
    setCustomGrowth,
    inflationPreset,
    setInflationPreset,
    yearsToRetirement,
    setYearsToRetirement,
    distributionYears,
    setDistributionYears,
    annualIncome,
    setAnnualIncome,
    assetValue,
    setAssetValue,
    blTau,
    setBlTau,
    blDelta,
    setBlDelta,
    equalWeights,
    setEqualWeights,
    marketWeights,
    setMarketWeights,
    views,
    setViews,
    applyRisk,
    setApplyRisk,
  } = form;

  const METHOD_OPTIONS: { value: OptimizeMethod; label: string }[] = [
    { value: "mvo", label: t.optimizer.methodMvo },
    { value: "resampled", label: t.optimizer.methodResampled },
    { value: "black-litterman", label: "Black-Litterman" },
    { value: "mean-cvar", label: "Mean-CVaR" },
    { value: "surplus", label: t.optimizer.methodSurplus },
    { value: "risk-parity", label: t.optimizer.methodRiskParity },
  ];

  const MODE_OPTIONS: { value: OptimizeMode; label: string }[] = [
    { value: "max-sharpe", label: t.optimizer.modeMaxSharpe },
    { value: "min-vol", label: t.optimizer.modeMinVol },
  ];

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 参数表单 ------------------------------ */}
      <Panel innerClassName="space-y-6">
        <Group label={t.optimizer.assetClassesLabel(assets.length)}>
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
          <Group label={t.optimizer.historyWindow}>
            <Segmented
              size="sm"
              options={OPTIMIZER_PERIOD_OPTIONS}
              value={period}
              onChange={setPeriod}
            />
          </Group>

          <Group label={t.optimizer.methodLabel}>
            <Segmented
              size="sm"
              options={METHOD_OPTIONS}
              value={method}
              onChange={setMethod}
            />
          </Group>

          <Group label={t.optimizer.objectiveLabel}>
            <span
              className={
                method === "risk-parity" ? "pointer-events-none opacity-50" : ""
              }
            >
              <Segmented
                size="sm"
                options={MODE_OPTIONS}
                value={mode}
                onChange={setMode}
              />
            </span>
            {method === "risk-parity" && (
              <span className="mt-1 block text-[11px] text-mist-600">
                {t.optimizer.rpModeHint}
              </span>
            )}
          </Group>

          <Group label={t.optimizer.riskFreeRate}>
            <div className="flex items-center gap-3 pt-0.5">
              <Toggle
                checked={rfAuto}
                onChange={setRfAuto}
                label={t.optimizer.rfAuto}
              />
              {!rfAuto && (
                <span className="flex items-center gap-1.5 text-sm text-mist-300">
                  <NumInput
                    aria-label={t.optimizer.rfManualAria}
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
          <span className="flex items-center gap-2.5">
            <span
              className={
                method === "risk-parity" ? "pointer-events-none opacity-50" : ""
              }
            >
              <Toggle
                checked={allowShort}
                onChange={setAllowShort}
                label={t.optimizer.allowShort}
              />
            </span>
            {method === "risk-parity" && (
              <span className="text-[11px] text-mist-600">
                {t.optimizer.rpShortHint}
              </span>
            )}
          </span>
          {method === "resampled" && (
            <Slider
              label={t.optimizer.simulations}
              value={nSim}
              min={50}
              max={1000}
              step={50}
              onChange={setNSim}
              className="w-56"
            />
          )}
          {method === "mean-cvar" && (
            <span className="flex flex-wrap items-center gap-2.5">
              <span className="text-xs text-mist-400">
                {t.optimizer.cvarConfidence}
              </span>
              <Segmented
                size="sm"
                options={CVAR_CONFIDENCE_OPTIONS}
                value={cvarConf}
                onChange={setCvarConf}
              />
              <span className="text-[11px] text-mist-600">
                {t.optimizer.cvarModeHint}
              </span>
            </span>
          )}
          <span className="flex items-center gap-2.5">
            <span className="text-xs text-mist-400">
              {t.optimizer.expectedReturnSource}
            </span>
            <span
              className={
                method === "black-litterman"
                  ? "pointer-events-none opacity-50"
                  : ""
              }
            >
              <Segmented
                size="sm"
                options={[
                  { value: "sample" as const, label: t.optimizer.sourceSample },
                  { value: "cme" as const, label: t.optimizer.sourceCme },
                ]}
                value={erSource}
                onChange={setErSource}
              />
            </span>
            {method === "black-litterman" && erSource === "cme" && (
              <span className="text-[11px] text-mist-600">
                {t.optimizer.cmeBlHint}
              </span>
            )}
          </span>
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
                  label={t.optimizer.clientRiskConstraint(clientName ?? "")}
                />
              </span>
              {method !== "mvo" && (
                <span className="text-[11px] text-mist-600">
                  {t.optimizer.mvoOnlyHint}
                </span>
              )}
            </span>
          ) : (
            <span className="text-[11px] text-mist-600">
              {t.optimizer.selectClientHint}
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

        {/* ------------------------- LDI 盈余配置面板 ------------------------- */}
        {method === "surplus" && (
          <SurplusConfigPanel
            assetClasses={assetClasses}
            hasClient={clientId !== null}
            clientName={clientName}
            source={surplusSource}
            setSource={setSurplusSource}
            liabilityRatio={liabRatio}
            setLiabilityRatio={setLiabRatio}
            liabilityDuration={liabDuration}
            setLiabilityDuration={setLiabDuration}
            proxy={surplusProxy}
            setProxy={setSurplusProxy}
            growthSource={growthSource}
            setGrowthSource={setGrowthSource}
            customGrowth={customGrowth}
            setCustomGrowth={setCustomGrowth}
            inflationPreset={inflationPreset}
            setInflationPreset={setInflationPreset}
            yearsToRetirement={yearsToRetirement}
            setYearsToRetirement={setYearsToRetirement}
            distributionYears={distributionYears}
            setDistributionYears={setDistributionYears}
            annualIncome={annualIncome}
            setAnnualIncome={setAnnualIncome}
            assetValue={assetValue}
            setAssetValue={setAssetValue}
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
            {loading ? t.optimizer.running : t.optimizer.run}
          </Button>
          {loading && (
            <span className="flex items-center gap-2 text-xs text-mist-500">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold-400" />
              {progressLabel ??
                (method === "resampled"
                  ? t.optimizer.progressResampled
                  : t.optimizer.progressSync)}
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
            title={t.optimizer.emptyTitle}
            hint={t.optimizer.emptyHint}
          />
        </Panel>
      )}
    </div>
  );
}
