export const advisor = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "AI Advisor",
  description:
    "Personalized investment proposals streamed token by token by DeepSeek, built on the client profile (IPS framework · behavioral finance · asset allocation).",

  // Config / demo banners
  notConfigured:
    "DEEPSEEK_API_KEY is not configured — set it in the project-root .env and restart the API service.",
  demoMode:
    "Demo mode — AI output is a recorded sample for feature preview; configure DEEPSEEK_API_KEY and turn off DEMO_MODE for live generation.",

  // Generation panel
  profilesUnreachable:
    "Could not load the profile list — please make sure the API service is running.",
  noProfilesPre: "No client profiles yet. Create one on the",
  noProfilesLink: "Profiles",
  noProfilesPost: "page first.",
  selectClient: "Client",
  profileOption: (name: string, age: number, risk: string | null) =>
    `${name} (${age}${risk ? ` · ${risk}` : ""})`,
  generateReport: "Generate Proposal",
  generating: "Generating…",
  stop: "Stop",
  model: "Model",

  // Report body
  reportTitle: "AI Investment Proposal",
  tokenSummary: (
    total: number,
    input: number,
    output: number,
    reasoning?: number
  ) =>
    `${total.toLocaleString()} tokens (in ${input.toLocaleString()} / out ${output.toLocaleString()}${
      reasoning ? ` · reasoning ${reasoning.toLocaleString()}` : ""
    })`,
  savedToLibrary: "Saved to report library",
  clientName: "Client Name",
  deliveryNotes: "Delivery Notes (optional)",
  notesPlaceholder: "A one-line note archived with the report…",
  saveToLibrary: "Save to Report Library",

  // Empty states
  thinking: "DeepSeek is reasoning…",
  streaming: "DeepSeek is generating…",
  idleTitle: "The proposal will stream in here",
  thinkingHint: "See the reasoning section above; the report body follows.",
  streamingHint: "The first tokens are on their way.",
  idleHint:
    "Pick a client and click “Generate Proposal” — the report streams out token by token and can be saved to the library in one click.",

  // Reasoning section (shared component)
  reasoningTitle: "Reasoning",
  reasoningTokens: (n: number) => `${n.toLocaleString()} reasoning tokens`,

  // Report library
  libraryTitle: "Saved Reports",
  libraryEmptyTitle: "No saved reports yet",
  libraryEmptyHint:
    "Generate a proposal and click “Save to Report Library” to revisit it here anytime.",
  thClient: "Client",
  thGenerated: "Generated",
  thActions: "Actions",
  viewReportLabel: "View report",
  deleteReportLabel: "Delete report",
  deleteTitle: "Delete this report?",
  deleteDescription:
    "The report will be permanently removed from the library. This cannot be undone.",

  // Error fallbacks
  requestFailed: (status: number) => `Request failed (HTTP ${status})`,
  validationFailed: "Report validation failed",
  generationInterrupted: "Generation interrupted",
  saveFailed: "Save failed",
  loadFailed: "Failed to load",
  deleteFailed: "Delete failed",
};
