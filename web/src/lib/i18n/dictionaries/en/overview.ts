/** overview namespace — populated by the localization pass (phase 22). */
export const overview = {
  title: "The Advisor's Cockpit",
  tagline:
    "Institutional-grade wealth management methodology × AI agents — the complete workflow from client profile to investment proposal.",
  workbenchTitle: "Workbench",
  monitoringOffender: (name: string, driftPp: number) =>
    `${name} drifted ${driftPp.toFixed(1)}pp`,
  monitoringBreachTitle: (n: number) =>
    `${n} portfolio${n === 1 ? "" : "s"} outside policy bands`,
  monitoringBreachHint: (asOf: string) =>
    `Rebalancing review recommended · Quotes as of ${asOf}`,
  monitoringOk: (n: number) =>
    `Portfolio monitoring healthy · all ${n} portfolio${n === 1 ? "" : "s"} within policy bands`,
  monitoringUnknown: (n: number) => `(${n} temporarily undetectable)`,
  monitoringAsOf: (asOf: string) => `Quotes as of ${asOf}`,
  monitoringUnavailable: "Portfolio monitoring data is temporarily unavailable",
  clientsTitle: "Clients at a Glance",
  clientsManage: "Manage",
  clientsOffline: "API offline — unable to load the client list.",
  clientsEmptyTitle: "No client profiles yet",
  clientsEmptyHint:
    "Create your first dual-track risk assessment profile to start the advisory workflow.",
  clientAge: (age: number) => `Age ${age}`,
  clientsTotal: (n: number) => `${n} client${n === 1 ? "" : "s"} in total`,
  deliverablesTitle: "Recent Deliverables",
  deliverablesOffline: "API offline — unable to load deliverables.",
  deliverablesEmptyTitle: "No deliverables yet",
  deliverablesEmptyHint:
    "Produce your first proposal for a client on the AI Advisor or IPS Generator pages.",
  kindAdvisor: "AI Proposal",
  kindIps: "IPS Document",
  /** resource prop for the shared <ApiOffline> panel (rendered mid-sentence). */
  offlineResource: "market and client data",
  disclaimer:
    "AI WealthPilot is a wealth-management prototype for research and educational use. All quantitative outputs and AI-generated content are based on historical data and model assumptions, and do not constitute investment advice.",
  modules: {
    market: {
      title: "Market",
      desc: "Global quotes, cross-asset correlation, and Capital Market Expectations (CME)",
    },
    optimizer: {
      title: "Optimizer",
      desc: "Efficient frontier solvers — MVO · Resampled · Black-Litterman",
    },
    retirement: {
      title: "Retirement",
      desc: "Two-stage life-cycle simulation powered by GBM Monte Carlo",
    },
    profiles: {
      title: "Profiles",
      desc: "Dual-track risk profiling with behavioral-bias detection",
    },
    advisor: {
      title: "Advisor",
      desc: "Streaming personalized investment proposals with DeepSeek",
    },
    ips: {
      title: "IPS Workflow",
      desc: "LangGraph multi-agent generate–review–revise pipeline",
    },
  },
};
