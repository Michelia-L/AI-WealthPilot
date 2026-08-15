"use client";

import { useState } from "react";
import type {
  BLViewInput,
  OptimizeMethod,
  OptimizeMode,
  OptimizeRequest,
  SurplusGrowthSource,
} from "@/lib/api";
import type { OptimizerDeepLink } from "@/lib/optimizer-link";
import { useClient } from "@/components/client-context";
import {
  type SurplusInflationPreset,
  type SurplusSource,
} from "./surplus-config-panel";

const DEFAULT_ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"];

/**
 * Form state machine for the optimizer workspace: every parameter field,
 * the asset toggle, and the OptimizeRequest builder. Execution (sync/async
 * run + SSE progress) lives in use-optimize-run.ts.
 */
export function useOptimizerForm({
  initialAssets,
  deepLink,
}: {
  initialAssets?: string[];
  deepLink?: OptimizerDeepLink;
}) {
  const [assets, setAssets] = useState<string[]>(
    initialAssets && initialAssets.length >= 2 ? initialAssets : DEFAULT_ASSETS
  );
  const [period, setPeriod] = useState("5y");
  const [method, setMethod] = useState<OptimizeMethod>(deepLink?.method ?? "mvo");
  const [mode, setMode] = useState<OptimizeMode>("max-sharpe");
  const [allowShort, setAllowShort] = useState(false);
  const [rfAuto, setRfAuto] = useState(true);
  const [rfManual, setRfManual] = useState("4.5");
  const [nSim, setNSim] = useState(200);
  const [cvarConf, setCvarConf] = useState(0.95);
  const [erSource, setErSource] = useState<"sample" | "cme">("sample");

  const [surplusSource, setSurplusSource] = useState<SurplusSource>(
    deepLink?.surplusSource ?? "manual"
  );
  const [liabRatio, setLiabRatio] = useState(1.0);
  const [liabDuration, setLiabDuration] = useState(10);
  const [surplusProxy, setSurplusProxy] = useState("US_BOND");
  const [growthSource, setGrowthSource] = useState<SurplusGrowthSource>("inflation");
  const [customGrowth, setCustomGrowth] = useState("3.0");
  const [inflationPreset, setInflationPreset] =
    useState<SurplusInflationPreset>("standard");
  const [yearsToRetirement, setYearsToRetirement] = useState(
    deepLink?.yearsToRetirement ?? 20
  );
  const [distributionYears, setDistributionYears] = useState(
    deepLink?.distributionYears ?? 25
  );
  const [annualIncome, setAnnualIncome] = useState(
    deepLink?.annualIncome !== undefined ? String(deepLink.annualIncome) : "80000"
  );
  const [assetValue, setAssetValue] = useState(
    deepLink?.assetValue !== undefined ? String(deepLink.assetValue) : "1000000"
  );

  const [blTau, setBlTau] = useState("0.025");
  const [blDelta, setBlDelta] = useState("2.5");
  const [equalWeights, setEqualWeights] = useState(true);
  const [marketWeights, setMarketWeights] = useState<Record<string, string>>(
    {}
  );
  const [views, setViews] = useState<BLViewInput[]>([]);

  // 全局客户上下文：选中客户后可把其风险等级注入为权重约束
  const { clientId } = useClient();
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
      // 风险平价仅多头（log-barrier 公式），切换方法时防御性复位
      allow_short: method === "risk-parity" ? false : allowShort,
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
    if (method === "mean-cvar") {
      body.cvar_confidence = cvarConf;
    }
    // BL 下 CME 作为先验（替代均衡收益），与 MVO/CVaR/LDI 同一开关
    if (erSource === "cme") {
      body.expected_return_source = "cme";
    }
    if (method === "surplus") {
      body.surplus = {
        proxy: surplusProxy,
        growth_source: growthSource,
        ...(growthSource === "custom"
          ? { custom_growth: (parseFloat(customGrowth || "0") || 0) / 100 }
          : {}),
        // 画像/退休+客户通道下通胀人群由后端按客户年龄自动建议
        ...(growthSource === "inflation" &&
        (surplusSource === "manual" ||
          (surplusSource === "retirement" && clientId === null))
          ? { inflation_preset: inflationPreset }
          : {}),
        ...(surplusSource === "manual"
          ? { liability_ratio: liabRatio, liability_duration: liabDuration }
          : surplusSource === "retirement"
            ? {
                years_to_retirement: yearsToRetirement,
                distribution_years: distributionYears,
                annual_income: parseFloat(annualIncome || "0") || 0,
                ...(clientId === null
                  ? { asset_value: parseFloat(assetValue || "0") || 0 }
                  : {}),
              }
            : {}),
      };
      // 画像通道取目标；退休通道取资产基数与年龄（通胀人群建议）
      if (
        (surplusSource === "profile" || surplusSource === "retirement") &&
        clientId !== null
      ) {
        body.profile_id = clientId;
      }
    }
    if (method === "mvo" && applyRisk && clientId !== null) {
      body.profile_id = clientId;
    }
    return body;
  }

  return {
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
    buildBody,
  };
}
