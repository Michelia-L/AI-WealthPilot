import type { InflationPreset } from "./retirement";
import type { PlotlyFigure } from "./market";
import { getJson } from "./client";

// ---------------------------------------------------------------------------
// Portfolio optimization
// ---------------------------------------------------------------------------

export interface AssetClassInfo {
  ticker: string;
  name: string;
}

export interface AssetClassesResponse {
  asset_classes: Record<string, AssetClassInfo>;
}

export interface BLViewInput {
  view_type: "absolute" | "relative";
  asset_long: string;
  asset_short?: string | null;
  expected_return: number;
  confidence: number;
}

export interface BLConfigInput {
  tau: number;
  delta: number;
  market_weights?: Record<string, number> | null;
  views: BLViewInput[];
}

export type OptimizeMethod = "mvo" | "resampled" | "black-litterman" | "mean-cvar" | "surplus" | "risk-parity";
export type OptimizeMode = "max-sharpe" | "min-vol";

export type SurplusGrowthSource = "inflation" | "risk_free" | "custom";

/** LDI 盈余优化输入（method=surplus）。 */
export interface SurplusConfigInput {
  /** 显式通道：k = 负债现值 / 资产价值。 */
  liability_ratio?: number | null;
  /** 显式通道：负债久期（年）。 */
  liability_duration?: number | null;
  /** 负债对冲代理（债券类资产键）。 */
  proxy?: string;
  growth_source?: SurplusGrowthSource;
  custom_growth?: number | null;
  inflation_preset?: InflationPreset | null;
  /** 退休收入流通道：距退休年数。 */
  years_to_retirement?: number | null;
  /** 退休收入流通道：支取年数。 */
  distribution_years?: number | null;
  /** 退休收入流通道：年收入（今日购买力）。 */
  annual_income?: number | null;
  /** 退休收入流通道：无画像时的资产基数。 */
  asset_value?: number | null;
}

/** 盈余优化实际采用的假设回显。 */
export interface SurplusInsight {
  liability_ratio: number;
  funding_ratio: number;
  liability_duration: number;
  liability_growth: number;
  discount_rate: number;
  discount_source: "china_treasury_curve" | "flat_risk_free";
  sigma_l_source: "china_treasury_curve" | "bond_proxy";
  proxy: string;
  source: "manual" | "profile" | "retirement";
  cash_flows: number | null;
  horizon_years: number | null;
}

export const SURPLUS_PROXY_OPTIONS = [
  "US_BOND",
  "LONG_TREASURY_BOND",
  "TIPS",
  "CN_TREASURY",
] as const;

export interface OptimizeRequest {
  assets: string[];
  period: string;
  risk_free_rate?: number | null;
  method: OptimizeMethod;
  mode: OptimizeMode;
  allow_short: boolean;
  n_simulations: number;
  /** CVaR 置信水平（仅 method=mean-cvar 时发送）。 */
  cvar_confidence?: number;
  /** 预期收益来源：历史样本均值 / CME 引擎（不适用于 black-litterman）。 */
  expected_return_source?: "sample" | "cme";
  bl?: BLConfigInput | null;
  /** LDI 负债参数（仅 method=surplus 时发送）。 */
  surplus?: SurplusConfigInput | null;
  /** 提供时按该客户的风险等级注入资产组权重上限（仅经典 MVO）。 */
  profile_id?: number | null;
}

export interface PortfolioResult {
  weights: Record<string, number>;
  ann_return: number;
  ann_volatility: number;
  sharpe: number;
  success: boolean;
  weight_std: Record<string, number> | null;
  /** mean-cvar 方法专属：该置信水平下的年化预期尾部损失。 */
  cvar?: number | null;
  /** risk-parity 方法专属：各资产对组合方差的风险贡献（合计为 1）。 */
  risk_contributions?: Record<string, number> | null;
}

export interface AssetStat {
  key: string;
  ticker: string;
  name: string;
  ann_return: number;
  ann_volatility: number;
}

export interface ViewImpact {
  label: string;
  impact: number;
}

export interface BLInsight {
  equilibrium_returns: Record<string, number>;
  posterior_returns: Record<string, number>;
  prior_source: "equilibrium" | "cme";
  prior_returns: Record<string, number> | null;
  warnings: string[];
  view_impacts: ViewImpact[];
  market_weights_source: "equal" | "aum" | "custom";
}

/** 按客户风险等级应用的资产组权重上限（method=mvo 时生效）。 */
export interface RiskConstraintsInfo {
  profile_id: number;
  profile_name: string;
  risk_level: string;
  caps: Record<string, number>;
}

export interface OptimizeResponse {
  as_of: string;
  params: {
    assets: string[];
    period: string;
    risk_free_rate: number;
    method: OptimizeMethod;
    mode: OptimizeMode;
    allow_short: boolean;
    n_simulations: number | null;
    cvar_confidence: number | null;
    expected_return_source?: "sample" | "cme";
    /** cme 模式下未被 CME 覆盖、回退为样本均值的资产显示名。 */
    cme_fallback_assets?: string[] | null;
    trading_days: number;
  };
  selected: PortfolioResult;
  max_sharpe: PortfolioResult;
  min_vol: PortfolioResult;
  frontier_chart: PlotlyFigure;
  allocation_chart: PlotlyFigure;
  asset_stats: AssetStat[];
  bl: BLInsight | null;
  surplus: SurplusInsight | null;
  risk_constraints?: RiskConstraintsInfo | null;
}

export const OPTIMIZER_PERIOD_OPTIONS = [
  { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" },
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" },
] as const;

export const getAssetClasses = () =>
  getJson<AssetClassesResponse>("/api/portfolio/asset-classes");

/** Personalized allocation from the risk-score-driven recommender (P12). */
export interface RecommendationResponse {
  profile_id: number;
  profile_name: string;
  risk_level: string;
  as_of: string;
  allocation: Record<string, number>;
  expected_return: number;
  expected_volatility: number;
  sharpe_ratio: number;
  rationale: string;
}

export const getRecommendation = (profileId: number) =>
  getJson<RecommendationResponse>(
    `/api/portfolio/recommendation?profile_id=${profileId}`
  );

