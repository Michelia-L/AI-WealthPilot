/** deliverables namespace — populated by the localization pass (phase 22). */
export const deliverables = {
  title: "Deliverables",
  description:
    "AI advisory reports and IPS documents in one place — every advisory deliverable, on record.",
  descriptionOffline:
    "Unified browsing and export of AI advisory reports and IPS documents.",
  resourceList: "the deliverables list",
  emptyTitle: "No deliverables match the filters",
  emptyHint:
    "Adjust the filters, or generate deliverables for a client on the AI Advisor / IPS pages first.",
  kindAdvisor: "AI Report",
  kindIps: "IPS",
  ipsSub: (version: string, status: string, rounds: number) =>
    `v${version} · ${status} · ${rounds} revision${rounds === 1 ? "" : "s"}`,
  colType: "Type",
  colClient: "Client",
  colSummary: "Summary",
  colTime: "Date",
  colActions: "Actions",
  filterClient: "Client",
  allClients: "All clients",
  filterType: "Type",
  typeAll: "All",
  typeIps: "IPS Documents",
  refreshing: "Refreshing…",
  countLabel: (n: number) => `${n} ${n === 1 ? "item" : "items"}`,
  backToCenter: "Back to Deliverables",
};
