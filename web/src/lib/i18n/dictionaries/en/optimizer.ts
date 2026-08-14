/** optimizer namespace — populated by the localization pass (phase 22). */
export const optimizer = {
  title: "Portfolio Optimizer",
  description:
    "Mean-variance optimization (MVO), Michaud resampled frontier, Black-Litterman Bayesian allocation, Mean-CVaR tail-risk optimization, LDI surplus optimization, and risk parity (ERC) — solving for optimal portfolios on the efficient frontier.",
  /** ApiOffline `resource` prop shown when the asset universe cannot load. */
  assetUniverse: "optimization asset universe",

  // ---- workspace form ----
  assetClassesLabel: (n: number) => `Asset Classes · ${n} selected (min 2)`,
  historyWindow: "Historical Window",
  methodLabel: "Method",
  objectiveLabel: "Objective",
  riskFreeRate: "Risk-Free Rate",
  rfAuto: "Auto-fetch",
  rfManualAria: "Manual risk-free rate (%)",
  methodMvo: "Classic MVO",
  methodResampled: "Resampled MVO",
  modeMaxSharpe: "Max Sharpe",
  modeMinVol: "Min Volatility",
  allowShort: "Allow Shorting",
  simulations: "Simulations",
  cvarConfidence: "CVaR Confidence",
  cvarModeHint:
    "Max Sharpe → max (return − rf) / CVaR; Min Volatility → min CVaR",
  expectedReturnSource: "Expected Returns",
  sourceSample: "Sample",
  sourceCme: "CME",
  cmeBlHint: "BL uses its own equilibrium returns",
  cmeFallbackHint: (names: string) =>
    `Not covered by the CME engine — sample means used for: ${names}`,
  clientRiskConstraint: (name: string) => `Client Risk Constraint (${name})`,
  mvoOnlyHint: "Classic MVO only",
  selectClientHint:
    "Select a client in the sidebar to inject their risk level as weight constraints",
  run: "Run Optimization",
  running: "Optimizing…",
  progressResampled: "Resampling task created, awaiting progress…",
  progressSync: "Fetching market data and solving…",
  emptyTitle: "Configure parameters and run an optimization",
  emptyHint:
    "Select at least 2 asset classes; results will show the efficient frontier, allocation weights, and key metrics.",

  // ---- workspace errors ----
  progressUnavailable: "Unable to receive task progress",
  optimizeFailed: "Optimization failed",
  streamEnded:
    "Task stream ended unexpectedly (the service may have restarted — please retry)",
  createTaskFailed: (status: number) =>
    `Failed to create task (HTTP ${status})`,
  requestFailed: (status: number) => `Request failed (HTTP ${status})`,

  // ---- Black-Litterman config ----
  blConfig: "Black-Litterman Configuration",
  blTau: "τ (Uncertainty Scaling)",
  blDelta: "δ (Risk Aversion Coefficient)",
  marketWeights: "Benchmark Weights",
  equalWeight: "Equal Weight (1/N)",
  customWeight: "Custom",
  marketWeightAria: (name: string) => `${name} benchmark weight (%)`,
  investorViews: (n: number) => `Investor Views (${n})`,
  addView: "Add View",
  viewsEmptyHint:
    "Black-Litterman requires at least one view. Absolute view: long an asset to a target return; relative view: A's excess return over B.",
  viewTypeAria: "View type",
  viewAbsolute: "Absolute",
  viewRelative: "Relative",
  longAssetAria: "Long asset",
  shortAssetAria: "Short asset",
  outperforms: "outperforms",
  expectedReturn: "Expected Return",
  excessReturn: "Excess",
  viewReturnAria: "View return (%)",
  confidence: "Confidence",
  deleteViewAria: "Delete view",

  // ---- Surplus (LDI) config ----
  methodSurplus: "Surplus (LDI)",
  surplusConfig: "Surplus (LDI) Configuration",
  surplusSource: "Liability Source",
  surplusSourceManual: "Manual",
  surplusSourceProfile: "From Client Profile",
  surplusProfileHint: (name: string) =>
    `Liabilities discounted from ${name}'s investment goals (asset base = investable assets)`,
  surplusNoClientHint:
    "Select a client in the sidebar to derive liabilities from their goals",
  surplusRatio: "Liability Ratio (L/A)",
  surplusDuration: "Liability Duration",
  durationYears: (v: number) => `${v} yrs`,
  surplusProxy: "Hedge Proxy",
  surplusGrowth: "Liability Growth",
  growthInflation: "Inflation-linked",
  growthRiskFree: "Risk-Free",
  growthCustom: "Custom",
  surplusCustomGrowthAria: "Custom liability growth (%)",
  surplusInflationSegment: "Inflation Segment",
  surplusPresetStandard: "Standard",
  surplusPresetElderly: "Elderly",
  surplusPresetLuxury: "Luxury",
  surplusAutoPresetHint:
    "The profile channel picks the segment by client age (elderly at 60+)",
  surplusAssumptionHint:
    "Liabilities are modeled by duration-scaling the bond proxy (approximate effective durations: AGG 6y, TLT 17y, TIP 7y); profile goals are discounted at the liability growth rate. These are stylized assumptions, not yield-curve pricing.",

  // ---- Risk parity (ERC) ----
  methodRiskParity: "Risk Parity (ERC)",
  rpModeHint: "Return-agnostic — objective N/A",
  rpShortHint: "Long-only",
  colRiskContribution: "Risk Contrib.",
  rpBenchmarkHint:
    "The Max Sharpe / Min Volatility panels show classic MVO benchmarks for comparison with the ERC portfolio.",

  // ---- results ----
  groupEquity: "Equity",
  groupBond: "Fixed Income",
  groupAlternative: "Alternatives",
  groupCash: "Cash",
  constraintsPrefix: "Weight constraints injected from ",
  constraintsSuffix: (level: string) => `'s risk level (${level})`,
  benchmarksUnconstrained:
    "Benchmarks (Max Sharpe / Min Volatility) are unconstrained",
  annReturn: "Annualized Return",
  annVolatility: "Annualized Volatility",
  sharpeRatio: "Sharpe Ratio",
  cvarLabel: (conf: number) =>
    `${Math.round(conf * 100)}% CVaR (ann. expected shortfall)`,
  fundingRatio: "Funding Ratio (A/L)",
  colAsset: "Asset",
  colAllocation: "Allocation",
  colWeightStd: "Weight σ",
  colEquilibrium: "Equilibrium Return",
  colPosterior: "Posterior Return",
  currentSelected: "Selected",
  returnLabel: "Return",
  volLabel: "Vol",
  sharpeLabel: "Sharpe",
  paramsSummary: (p: {
    period: string;
    tradingDays: number;
    riskFreeRate: string;
    allowShort: boolean;
    nSimulations: number | null;
  }) =>
    `Params: ${p.period} window · ${p.tradingDays} trading days · risk-free rate ${p.riskFreeRate} · ${
      p.allowShort ? "shorting allowed" : "long only"
    }${p.nSimulations ? ` · ${p.nSimulations} resamples` : ""}`,
  surplusAssumptions: (p: {
    source: string;
    ratio: string;
    duration: string;
    growth: string;
    proxy: string;
  }) =>
    `LDI assumptions: ${p.source} · L/A=${p.ratio} · duration ${p.duration} · growth ${p.growth} · proxy ${p.proxy}`,

  // ---- backtest ----
  backtestTitle: "Portfolio Backtest",
  backtestSubtitle:
    "Validate these weights against history (monthly rebalancing)",
  backtestRun: "Backtest This Portfolio",
  backtestRerun: "Re-run Backtest",
  backtestRunning: "Backtesting…",
  backtestFetching: "Fetching historical prices and simulating NAV…",
  backtestFailed: (status: number) => `Backtest failed (HTTP ${status})`,
};
