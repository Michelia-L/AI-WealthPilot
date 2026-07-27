/** monitoring namespace — populated by the localization pass (phase 22). */
export const monitoring = {
  title: "Portfolio Monitor",
  description:
    "Anchored to the strategic asset allocation (SAA): buy-and-hold drift, band deviations, and rebalancing guidance.",
  descriptionOffline:
    "Drift monitoring and rebalancing guidance anchored to SAA target weights.",
  resourceIpsList: "the IPS document list",
  resourceMonitoring:
    "monitoring data (the document may be missing an SAA, or the API may be offline)",
  resourceBacktest:
    "backtest data (market history is unavailable, or the document lacks an SAA)",
  emptyTitle: "Select an IPS document to start monitoring",
  emptyHint:
    "Monitoring uses the document's strategic allocation (target weights and bounds) as the baseline and computes drift against the latest market data.",
  ipsSavedAt: (when: string) => `IPS saved ${when}`,
  asOf: (when: string) => `As of ${when}`,
  cmeCache: (status: string) => `CME cache: ${status}`,
  analyzeInOptimizer: "Analyze in Optimizer",
  statReturnTarget: "Expected Return (Target)",
  statVolTarget: "Portfolio Volatility (Target)",
  statSharpeTarget: "Portfolio Sharpe (Target)",
  driftedHint: (value: string) => `Drifted ${value}`,
  driftPanelTitle: "Weight Drift vs. Allocation Bands",
  driftLegend:
    "Gold bar = current (drifted) · Tick = target · Light band = allowed range",
  barTitle: (target: string, min: string, max: string) =>
    `Target ${target} · Band ${min}–${max}`,
  bandWithin: "Within band",
  bandAbove: "Above limit",
  bandBelow: "Below limit",
  bandUnknown: "No data",
  rebalanceTitle: "Rebalancing",
  rebalanceNone:
    "All holdings are within their allocation bands — no rebalancing needed.",
  actionBuy: "Buy",
  actionSell: "Sell",
  colAsset: "Asset Class",
  colExpectedReturn: "Expected Return",
  colVolatility: "Volatility",
  colSharpe: "Sharpe",
  colMaxDrawdown: "Max Drawdown",
  colPeriodReturn: "Period Return",
  notesTitle: "Data Notes",
  adviceTitle: "AI Rebalancing Advice",
  adviceStop: "Stop",
  adviceGenerate: "Generate Advice",
  adviceRegenerate: "Regenerate",
  adviceEmptyTitle: "Let AI interpret this monitoring snapshot",
  adviceEmptyHint:
    "Generates rebalancing rationale, execution pacing, and risk warnings from the drift diagnosis and proposed trades. Incorporates the selected client's risk profile when one is chosen.",
  adviceStreaming: "DeepSeek is analyzing the monitoring results…",
  adviceRequestFailed: (status: number) => `Request failed (HTTP ${status})`,
  adviceGenerateFailed: "Generation failed",
  backtestTitle: "Historical Backtest",
  backtestSub: (benchmark: string) => `Monthly rebalancing · vs. ${benchmark}`,
};
