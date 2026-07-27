/** optimizer namespace — populated by the localization pass (phase 22). */
export const optimizer = {
  title: "Portfolio Optimizer",
  description:
    "Mean-variance optimization (MVO), Michaud resampled frontier, and Black-Litterman Bayesian allocation — solving for optimal portfolios on the efficient frontier.",
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
  marketWeights: "Market-Cap Weights",
  equalWeight: "Equal Weight (1/N)",
  customWeight: "Custom",
  marketWeightAria: (name: string) => `${name} market-cap weight (%)`,
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
