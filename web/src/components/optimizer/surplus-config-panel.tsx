"use client";

import type {
  AssetClassInfo,
  InflationPreset,
  SurplusGrowthSource,
} from "@/lib/api";
import { SURPLUS_PROXY_OPTIONS } from "@/lib/api";
import { useT } from "@/components/locale-context";
import Icon from "../ui/icon";
import Panel from "../ui/panel";
import Segmented from "../ui/segmented";
import Slider from "../ui/slider";
import { NumInput, Select } from "../ui/field";
import Group from "./group";

export type SurplusSource = "manual" | "profile" | "retirement";
/** 面板里只允许三个内置 preset；custom 走 retirement 的自定义滑杆语义，此处不支持。 */
export type SurplusInflationPreset = Exclude<InflationPreset, "custom">;

interface SurplusConfigPanelProps {
  assetClasses: Record<string, AssetClassInfo>;
  hasClient: boolean;
  clientName: string | null;
  source: SurplusSource;
  setSource: (v: SurplusSource) => void;
  liabilityRatio: number;
  setLiabilityRatio: (v: number) => void;
  liabilityDuration: number;
  setLiabilityDuration: (v: number) => void;
  proxy: string;
  setProxy: (v: string) => void;
  growthSource: SurplusGrowthSource;
  setGrowthSource: (v: SurplusGrowthSource) => void;
  customGrowth: string;
  setCustomGrowth: (v: string) => void;
  inflationPreset: SurplusInflationPreset;
  setInflationPreset: (v: SurplusInflationPreset) => void;
  yearsToRetirement: number;
  setYearsToRetirement: (v: number) => void;
  distributionYears: number;
  setDistributionYears: (v: number) => void;
  annualIncome: string;
  setAnnualIncome: (v: string) => void;
  assetValue: string;
  setAssetValue: (v: string) => void;
}

/** LDI 盈余优化配置面板 —— 负债来源、对冲代理、负债增长率。 */
export default function SurplusConfigPanel({
  assetClasses,
  hasClient,
  clientName,
  source,
  setSource,
  liabilityRatio,
  setLiabilityRatio,
  liabilityDuration,
  setLiabilityDuration,
  proxy,
  setProxy,
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
}: SurplusConfigPanelProps) {
  const t = useT();

  return (
    <Panel innerClassName="space-y-5 p-5">
      <div className="text-[11px] font-medium tracking-[0.18em] text-gold-400/90 uppercase">
        {t.optimizer.surplusConfig}
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <Group label={t.optimizer.surplusSource}>
          <Segmented
            size="sm"
            options={[
              { value: "manual" as const, label: t.optimizer.surplusSourceManual },
              { value: "profile" as const, label: t.optimizer.surplusSourceProfile },
              { value: "retirement" as const, label: t.optimizer.surplusSourceRetirement },
            ]}
            value={source}
            onChange={(v) => {
              if (v === "profile" && !hasClient) return;
              setSource(v);
            }}
          />
        </Group>

        <Group label={t.optimizer.surplusProxy}>
          <Select
            aria-label={t.optimizer.surplusProxy}
            value={proxy}
            onChange={(e) => setProxy(e.target.value)}
            className="py-1.5 text-xs"
          >
            {SURPLUS_PROXY_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {assetClasses[k]?.name ?? k}
              </option>
            ))}
          </Select>
        </Group>

        <Group label={t.optimizer.surplusGrowth}>
          <Segmented
            size="sm"
            options={[
              { value: "inflation" as const, label: t.optimizer.growthInflation },
              { value: "risk_free" as const, label: t.optimizer.growthRiskFree },
              { value: "custom" as const, label: t.optimizer.growthCustom },
            ]}
            value={growthSource}
            onChange={setGrowthSource}
          />
        </Group>
      </div>

      {source === "profile" && hasClient && (
        <p className="flex items-center gap-1.5 text-xs text-mist-500">
          <Icon name="users" size={13} className="text-gold-400" />
          {t.optimizer.surplusProfileHint(clientName ?? "")}
        </p>
      )}
      {!hasClient && source !== "retirement" && (
        <p className="text-xs text-mist-600">{t.optimizer.surplusNoClientHint}</p>
      )}

      {source === "manual" && (
        <div className="grid gap-5 md:grid-cols-2">
          <Slider
            label={t.optimizer.surplusRatio}
            value={liabilityRatio}
            min={0.1}
            max={3}
            step={0.05}
            onChange={setLiabilityRatio}
            format={(v) => v.toFixed(2)}
          />
          <Slider
            label={t.optimizer.surplusDuration}
            value={liabilityDuration}
            min={1}
            max={30}
            step={1}
            onChange={setLiabilityDuration}
            format={t.optimizer.durationYears}
          />
        </div>
      )}

      {source === "retirement" && (
        <>
          <div className="grid gap-5 md:grid-cols-3">
            <Slider
              label={t.optimizer.yearsToRetirement}
              value={yearsToRetirement}
              min={0}
              max={50}
              step={1}
              onChange={setYearsToRetirement}
              format={t.optimizer.durationYears}
            />
            <Slider
              label={t.optimizer.distributionYears}
              value={distributionYears}
              min={1}
              max={60}
              step={1}
              onChange={setDistributionYears}
              format={t.optimizer.durationYears}
            />
            <Group label={t.optimizer.annualIncome}>
              <NumInput
                min={0}
                step={10000}
                value={annualIncome}
                onChange={(e) => setAnnualIncome(e.target.value)}
              />
            </Group>
          </div>
          {hasClient ? (
            <p className="flex items-center gap-1.5 text-xs text-mist-500">
              <Icon name="users" size={13} className="text-gold-400" />
              {t.optimizer.surplusProfileBaseHint}
            </p>
          ) : (
            <Group label={t.optimizer.assetValueLabel}>
              <NumInput
                min={0}
                step={100000}
                value={assetValue}
                onChange={(e) => setAssetValue(e.target.value)}
                className="w-44"
              />
            </Group>
          )}
        </>
      )}

      {growthSource === "inflation" &&
        (source === "profile" || (source === "retirement" && hasClient) ? (
          <p className="text-[11px] text-mist-600">
            {t.optimizer.surplusAutoPresetHint}
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-xs text-mist-400">
              {t.optimizer.surplusInflationSegment}
            </span>
            <Segmented
              size="sm"
              options={[
                { value: "standard" as const, label: t.optimizer.surplusPresetStandard },
                { value: "elderly" as const, label: t.optimizer.surplusPresetElderly },
                { value: "luxury" as const, label: t.optimizer.surplusPresetLuxury },
              ]}
              value={inflationPreset}
              onChange={setInflationPreset}
            />
          </div>
        ))}

      {growthSource === "custom" && (
        <span className="flex items-center gap-1.5 text-sm text-mist-300">
          <NumInput
            aria-label={t.optimizer.surplusCustomGrowthAria}
            step="0.1"
            min="-10"
            max="30"
            value={customGrowth}
            onChange={(e) => setCustomGrowth(e.target.value)}
            className="w-24 px-2 py-1 text-xs"
          />
          %
        </span>
      )}

      <p className="border-t border-white/[0.05] pt-3 text-[11px] leading-5 text-mist-600">
        {t.optimizer.surplusAssumptionHint}
      </p>
    </Panel>
  );
}
