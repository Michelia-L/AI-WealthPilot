/** profileDetail namespace — /profiles/[id] client hub page and hub actions. */
export const profileDetail = {
  title: "Client Hub",
  invalidId: "Invalid client ID",
  backToList: "Back to Client List",
  detailResource: "client details (the client may not exist, or the API is offline)",
  headerDescription: (
    age: number,
    marital: string,
    dependents: number,
    updated: string
  ) => `Age ${age} · ${marital} · ${dependents} dependents · Updated ${updated}`,
  editProfile: "Edit Profile",
  // Hub actions
  currentClient: "Current Client",
  setAsCurrentClient: "Set as Current Client",
  generateReport: "Generate Proposal",
  generateIps: "Generate IPS",
  // Key metrics
  netWorth: "Net Worth",
  savingsRate: "Annual Savings Rate",
  annualSavingsHint: (amount: string) => `Annual savings ${amount}`,
  debtToAssetRatio: "Debt-to-Asset Ratio",
  finalRiskScore: "Composite Risk Score",
  finalRiskScoreHint: "min(ability, willingness) · out of 5",
  // Financial situation panel
  financials: "Financial Situation",
  annualIncome: "Annual Income",
  annualExpenses: "Annual Expenses",
  investableAssets: "Investable Assets",
  totalLiabilities: "Total Liabilities",
  emergencyFund: "Emergency Fund",
  // Risk profile panel
  riskProfile: "Risk Profile",
  abilityScoreLabel: "Ability to Take Risk (Objective)",
  willingnessScoreLabel: "Willingness to Take Risk (Subjective)",
  // Goals panel
  goals: "Investment Goals",
  noGoals: "No investment goals set yet.",
  yearsLater: (n: number) => `In ${n} years`,
  priorityBadge: (v: string): string =>
    v === "high"
      ? "High Priority"
      : v === "low"
        ? "Low Priority"
        : "Medium Priority",
  // Constraints panel
  constraints: "Constraints & Preferences",
  timeHorizon: "Time Horizon",
  horizonValue: (years: number, multiStage: boolean) =>
    `${years} years${multiStage ? " (multi-stage)" : ""}`,
  liquidityNeeds: "Liquidity Needs",
  taxStatus: "Tax Status",
  esgPreference: "ESG Preference",
  esgYes: "Yes",
  esgNo: "No",
  sectorRestrictions: "Sector Restrictions",
  none: "None",
  // Recommendation section
  recommendation: "Recommended Allocation",
  expectedReturn: "Expected Return",
  expectedVolatility: "Expected Volatility",
  sharpeRatio: "Sharpe Ratio",
  // Deliverables panel
  deliverables: "Deliverables",
  deliverableCount: (n: number) => `${n} items`,
  advisorReport: "AI Proposal",
  deliverablesEmptyTitle: "No deliverables yet",
  deliverablesEmptyHint:
    'Use "Generate Proposal" or "Generate IPS" above to produce this client\'s first deliverable.',
  // Shared domain labels
  unassessed: "Not assessed",
  monthsValue: (n: number) => `${n} months`,
  maritalLabel: (v: string) =>
    v === "single"
      ? "Single"
      : v === "married"
        ? "Married"
        : v === "divorced"
          ? "Divorced"
          : v === "widowed"
            ? "Widowed"
            : v,
  taxLabel: (v: string) =>
    v === "taxable"
      ? "Taxable Account"
      : v === "tax-exempt"
        ? "Tax-Exempt Account"
        : v === "tax-deferred"
          ? "Tax-Deferred Account"
          : v,
};
