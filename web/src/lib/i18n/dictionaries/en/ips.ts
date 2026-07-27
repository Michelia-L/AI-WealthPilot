export const ips = {
  /** Page title (h1 + metadata); also the other locale's eyebrow. */
  title: "IPS Workflow",
  description:
    "LangGraph multi-agent workflow: capital market expectations feed the first draft, which then passes suitability, compliance and consistency reviews plus SAA quantitative validation, with automatic revisions until final sign-off and archival.",

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
  selectProfile: "Profile",
  profileOption: (name: string, age: number, risk: string | null) =>
    `${name} (${age}${risk ? ` · ${risk}` : ""})`,
  maxRevisions: "Max Revision Rounds",
  generate: "Generate IPS",
  running: "Workflow Running…",
  pipelineHint:
    "CME → first draft → three-pillar review → SAA quantitative validation → revise/finalize (usually takes a few minutes)",

  // Progress timeline
  progressTitle: "Workflow Progress",
  processing: "Processing…",
  donePre: "IPS generated and archived · Document",
  statusLabel: "Status",
  doneRevisions: (n: number) => ` · ${n} revision${n === 1 ? "" : "s"}`,
  viewNow: "View Now",

  // Document viewer
  version: "Version",
  revisionRounds: "Revision Rounds",
  downloadPdf: "Download PDF",

  // Document library
  libraryTitle: "IPS Documents",
  libraryHint: "Stored as local JSON",
  libraryEmptyTitle: "No IPS documents yet",
  libraryEmptyHint:
    "Select a client profile and run the workflow above — generated IPS documents will be saved here.",
  thClient: "Client",
  thRisk: "Risk Level",
  thRevisions: "Revisions",
  thSaved: "Saved",
  thActions: "Actions",

  // Error fallbacks
  createTaskFailed: (status: number) => `Failed to create task (HTTP ${status})`,
  progressUnavailable: "Could not receive task progress",
  generateFailed: "Generation failed",
  loadFailed: "Failed to load",
};
