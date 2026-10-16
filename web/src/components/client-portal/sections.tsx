import Link from "next/link";
import GoalFundingCards from "@/components/goal-funding-cards";
import {
  Badge,
  EmptyState,
  SectionHeader,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import type {
  ClientAllocation,
  ClientGoal,
  ClientReportSummary,
} from "@/lib/api/client-portal";
import { fmtPct, fmtUtc } from "@/lib/format";
import { getDict } from "@/lib/i18n/server";

export async function ClientPage({
  section,
  children,
}: {
  section: "overview" | "portfolio" | "goals" | "risk" | "documents" | "ai";
  children: React.ReactNode;
}) {
  const t = (await getDict()).clientPortal;
  return (
    <div className="space-y-8">
      <SectionHeader
        eyebrow={t.name}
        title={t.nav[section]}
        description={t.description[section]}
      />
      {children}
    </div>
  );
}

export async function Allocation({
  allocation,
}: {
  allocation: ClientAllocation[];
}) {
  const t = (await getDict()).clientPortal;
  if (!allocation.length)
    return <EmptyState icon="pie" title={t.noPlan} hint={t.noPlanHint} />;
  return (
    <Table>
      <caption className="sr-only">{t.targetAllocation}</caption>
      <THead>
        <tr>
          <TH>{t.assetClass}</TH>
          <TH className="text-right">{t.targetWeight}</TH>
        </tr>
      </THead>
      <tbody>
        {allocation.map((item) => (
          <TR key={item.asset_class}>
            <TD>
              <span className="break-words">{item.asset_class}</span>
              <div
                aria-hidden
                className="mt-2 h-1.5 w-full max-w-64 rounded-full bg-ink-800"
              >
                <div
                  className="h-full rounded-full bg-gold-500"
                  style={{ width: fmtPct(item.weight) }}
                />
              </div>
            </TD>
            <TD className="text-right font-mono">{fmtPct(item.weight, 1)}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

export async function GoalCards({ goals }: { goals: ClientGoal[] }) {
  return <GoalFundingCards goals={goals} t={(await getDict()).goalTracking} />;
}

export async function ReportList({
  reports,
}: {
  reports: ClientReportSummary[];
}) {
  const t = (await getDict()).clientPortal;
  if (!reports.length)
    return (
      <EmptyState
        icon="scroll"
        title={t.noDocuments}
        hint={t.noDocumentsHint}
      />
    );
  return (
    <ul className="divide-y divide-white/[0.06]">
      {reports.map((report) => (
        <li key={report.id}>
          <Link
            href={`/client/documents/${encodeURIComponent(report.id)}`}
            className="group flex flex-wrap items-center justify-between gap-3 py-5"
          >
            <span className="min-w-0 flex-1">
              <span className="block break-words font-medium text-mist-100 group-hover:text-gold-300">
                {report.title}
              </span>
              <span className="mt-1 block text-xs leading-6 text-mist-400">
                {t.documentTypes[report.type]} · {t.version(report.version)} ·{" "}
                {fmtUtc(report.published_at)}
              </span>
            </span>
            <Badge tone={report.status === "acknowledged" ? "jade" : "gold"}>
              {t.statuses[report.status]}
            </Badge>
          </Link>
        </li>
      ))}
    </ul>
  );
}
