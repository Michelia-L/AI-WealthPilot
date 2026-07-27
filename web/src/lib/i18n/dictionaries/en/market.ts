/** market namespace — populated by the localization pass (phase 22). */
export const market = {
  title: "Market Dashboard",
  description:
    "Real-time quotes, cross-asset correlation, and Capital Market Expectations (CME).",
  footerDisclaimer:
    "Data source: Yahoo Finance (yfinance); real-time quotes are cached for 5 minutes. Quantitative outputs are for reference only and do not constitute investment advice.",
  /** resource props for the shared <ApiOffline> panel (rendered mid-sentence). */
  offlineUniverse: "asset universe metadata",
  offlineAnalytics: "analytics data",
  offlineQuotes: "quote data",
  offlineCme: "Capital Market Expectations (CME)",
  snapshotTitle: "Market Snapshot",
  breadthUp: (n: number) => `Up ${n}`,
  breadthDown: (n: number) => `Down ${n}`,
  breadthFlat: (n: number) => `Flat ${n}`,
  breadthBest: "Top gainer",
  breadthWorst: "Top loser",
  cmeTitle: "Capital Market Expectations",
  cmeMeta: (
    asOf: string,
    riskFreeRate: string,
    source: string,
    lookbackYears: number
  ) =>
    `Data as of ${asOf} · Risk-free rate ${riskFreeRate} (${source}) · ${lookbackYears}-year lookback`,
  tabPrice: "Price Trend",
  tabCorrelation: "Asset Correlation",
  tabStats: "Risk Statistics",
  normalizeToggle: "Normalize (Base = 100)",
  correlationEmpty:
    "At least 2 assets are required to compute the correlation matrix.",
  corrGuideTitle: "Interpretation",
  corrGuideSubtitle: "Diversification Analysis",
  corrRedLabel: "Red (+1.0)",
  corrRedDesc: ": Highly positive correlation — assets rise and fall together.",
  corrBlueLabel: "Blue (−1.0)",
  corrBlueDesc: ": Highly negative correlation — an excellent hedging pair.",
  corrWhiteLabel: "White (0.0)",
  corrWhiteDesc: ": No correlation — pure diversification benefit.",
  corrTip:
    "Tip: building a portfolio with low-correlation assets can maximize the Sharpe ratio.",
  thAsset: "Asset",
  thAssetClass: "Asset Class",
  thAnnReturn: "Annualized Return",
  thAnnVol: "Annualized Volatility",
  thExpectedReturn: "Expected Return",
  thBlendedVol: "Blended Vol (IV)",
  thSharpe: "Sharpe",
  thMaxDrawdown: "Max Drawdown",
  thDailyVar: "Daily VaR (95%)",
  thVolRegime: "Volatility Regime",
};
