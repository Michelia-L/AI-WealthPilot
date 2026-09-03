/** profiles namespace — /profiles list, manager, form, compare, questionnaire. */
export const profiles = {
  title: "Client Profiles",
  description:
    "Client information management under the IPS framework: the dual-track risk assessment takes min(ability, willingness) as the final risk level.",
  createProfile: "New Profile",
  deleteDialogTitle: "Delete Client Profile",
  deleteDialogDescription: (name: string) =>
    `Delete profile "${name}"? This action cannot be undone.`,
  // Async action fallbacks (server detail messages pass through untouched)
  errorCompareFailed: "Comparison failed",
  errorLoadFailed: "Failed to load",
  errorValidationFailed: "Validation failed",
  errorListSeparator: "; ",
  errorSaveFailed: (status: number) => `Save failed (HTTP ${status})`,
  errorDeleteFailed: "Failed to delete",
  errorImportFailed: "Import failed",
  importSummary: (found: number, imported: number, skipped: number) =>
    `Import complete: found ${found} JSON files, added ${imported}, skipped ${skipped}.`,
  uploadJson: "Upload JSON",
  uploadInvalid: (files: string) => `Files failed validation: ${files}`,
  // Form
  editFormTitle: (name: string) => `Edit Profile · ${name || "…"}`,
  sectionBasicInfo: "Basic Information",
  fieldName: "Name",
  namePlaceholder: "e.g. Zhang San",
  fieldAge: "Age",
  fieldMaritalStatus: "Marital Status",
  fieldDependents: "Dependents",
  sectionFinancials: "Financial Situation",
  fieldAnnualIncome: "Annual Income",
  fieldAnnualExpenses: "Annual Expenses",
  fieldInvestableAssets: "Investable Assets",
  fieldTotalLiabilities: "Total Liabilities",
  fieldEmergencyFundMonths: "Emergency Fund (months)",
  sectionGoals: "Investment Goals",
  addGoal: "Add Goal",
  noGoalsYet: "No goals yet — use the button in the top-right to add one.",
  fieldGoalName: "Goal Name",
  goalNamePlaceholder: "e.g. Retirement",
  fieldTargetAmount: "Target Amount",
  fieldYears: "Years",
  fieldPriority: "Priority",
  deleteGoalAria: "Delete goal",
  sectionConstraints: "Investment Constraints & Preferences",
  fieldTimeHorizon: "Time Horizon (years)",
  fieldLiquidityNeeds: "Liquidity Needs (amount)",
  fieldTaxStatus: "Tax Status",
  fieldSectorRestrictions: "Sector Restrictions (comma-separated)",
  sectorRestrictionsPlaceholder: "e.g. Tobacco, Defense",
  esgPreferenceLabel: "ESG Preference (Environmental / Social / Governance)",
  fieldNotes: "Notes",
  sectionQuestionnaire: "Risk Questionnaire",
  saveChanges: "Save Changes",
  // List
  importFromJson: "Import from JSON",
  comparing: "Comparing…",
  compareSelected: (n: number) => `Compare Selected (${n})`,
  selectOneMoreHint: (max: number) =>
    `Select 1 more to compare (up to ${max})`,
  listResource: "the profile list",
  emptyTitle: "No client profiles yet",
  emptyHint:
    "Build your first dual-track risk-assessment profile, or import JSON files from the Streamlit era.",
  selectSrOnly: "Select",
  colRiskLevel: "Risk Level",
  colUpdated: "Updated",
  colActions: "Actions",
  selectForCompareAria: (name: string) => `Select ${name} for comparison`,
  editAria: (name: string) => `Edit ${name}`,
  deleteAria: (name: string) => `Delete ${name}`,
  // Compare
  compareTitle: "Profile Comparison",
  colClient: "Client",
  colRiskScore: "Risk Score",
  colNetWorth: "Net Worth",
  colSavingsRate: "Savings Rate",
  colEmergencyFund: "Emergency Fund",
  colBiasCount: "Biases",
  keyInsights: "Key Insights",
  biasAnalysis: "Behavioral Bias Analysis",
  noBiasesDetected: "No behavioral biases detected",
  // Questionnaire
  riskAbility: "Ability to Take Risk",
  riskWillingness: "Willingness to Take Risk",
  combinedScore: "Combined = min(ability, willingness)",
  livePreview: "Live Preview",
  abilityTrackTitle: "Ability to Take Risk (Objective · 5 questions)",
  willingnessTrackTitle: "Willingness to Take Risk (Subjective · 4 questions)",
  questionnaireHelp:
    "Answered questions are scored automatically (unanswered questions are excluded from the average) and overwrite the manual scores on save; click a selected option again to clear it. Leave all questions blank to keep the manual scores — 0 means not assessed.",
  questionnaireUnavailable:
    "The risk questionnaire failed to load (API not ready); manual scores are used instead for now — a score of 0 means not assessed.",
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
  priorityShort: (v: string): string =>
    v === "high" ? "High" : v === "low" ? "Low" : "Medium",
};
