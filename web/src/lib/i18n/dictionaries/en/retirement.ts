/** retirement namespace — populated by the localization pass (phase 22). */
export const retirement = {
  title: "Retirement Planner",
  description:
    "Two-phase geometric Brownian motion Monte Carlo: steady savings injections during accumulation, inflation-adjusted withdrawals during distribution — evaluating the probability that retirement funds endure.",

  currentAge: "Current Age",
  retirementAge: "Retirement Age",
  lifeExpectancy: "Life Expectancy",
  ageYears: (v: number) => `${v} yrs`,
  currentSavings: "Current Savings",
  annualSavings: "Annual Savings",
  desiredIncome: "Desired Annual Income in Retirement",
  expectedReturn: "Expected Annual Return",
  volatility: "Annualized Volatility",
  inflationRate: "Inflation Rate",
  inflationSegment: "Spending Segment",
  inflationPresetStandard: "Standard",
  inflationPresetElderly: "Elderly",
  inflationPresetLuxury: "Luxury",
  inflationPresetCustom: "Custom",
  distributionInflationRate: "Distribution-Phase Inflation",
  distributionInflationHint:
    "Withdrawals after retirement use a segment-adjusted rate (CPI-E / CLEWI style); the applied rate appears in the result parameters below",
  distributionInflationShort: "dist. inflation",
  simulationCount: "Simulations",
  run: "Run Simulation",
  running: "Simulating…",
  ageConstraint: "Requires: current age < retirement age < life expectancy",
  requestFailed: (status: number) => `Request failed (HTTP ${status})`,

  survivalRate: "Plan Survival Rate",
  survivalSteady: "On Track",
  survivalWatch: "Needs Attention",
  survivalRisk: "At Risk",
  medianAtRetirement: "Median Assets at Retirement",
  accumulationPhase: "Accumulation",
  distributionPhase: "Distribution",
  durationYears: (n: number) => `${n} yrs`,

  depletionTitle: "Depletion Analysis",
  neverDepleted: "Never Depleted",
  depletedWithin10y: "Depleted Within 10 Years",
  medianDepletionYear: "Median Depletion Year",
  yearNth: (y: string) => `Year ${y}`,

  quantileTableTitle: "Asset Quantiles at Retirement",
  meanLabel: "Mean",
  terminalDistribution: "Terminal Distribution",

  sensitivityTitle: "Sensitivity Analysis",
  sensitivitySubtitle: "— How annual savings affect the survival rate",
  survivalRateShort: "Survival Rate",
  currentBadge: "Current",

  paramsPrefix: "Params: ",
  expectedReturnShort: "expected return",
  volatilityShort: "volatility",
  inflationShort: "inflation",
  simulationsShort: (n: string) => `${n} simulations`,
  seedNote: (seed: number) => `seed=${seed} (reproducible)`,

  emptyTitle: "Set Parameters & Run the Simulation",
  emptyHint:
    "Runs 10,000 geometric Brownian motion paths by default, spanning both the accumulation and distribution phases, and outputs survival rate, asset distribution, and savings sensitivity.",
};
