import {
  Allocation,
  ClientPage,
  GoalCards,
  ReportList,
} from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import { Badge, ButtonLink, Panel, StatTile } from "@/components/ui";
import {
  getClientAdvisors,
  getClientGoals,
  getClientPortfolio,
  getClientProfile,
  getClientReports,
  getClientRisk,
} from "@/lib/api/server";
import { fmtLocal, fmtMoney } from "@/lib/format";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientOverview() {
  const locale = await getLocale();
  const t = (await getDict()).clientPortal;
  const [profile, portfolio, goals, risk, reports, advisors] =
    await Promise.all([
      getClientProfile(locale),
      getClientPortfolio(locale),
      getClientGoals(locale),
      getClientRisk(locale),
      getClientReports(locale, 0, 5),
      getClientAdvisors(locale),
    ]);
  return (
    <ClientPage section="overview">
      {profile.data ? (
        <Panel>
          <h2 className="mb-5 font-display text-2xl">
            {t.welcome(profile.data.name)}
          </h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile
              label={t.netWorth}
              value={fmtMoney(profile.data.net_worth, "")}
              tone="gold"
            />
            <StatTile
              label={t.investableAssets}
              value={fmtMoney(profile.data.investable_assets, "")}
            />
            <StatTile
              label={t.liabilities}
              value={fmtMoney(profile.data.total_liabilities, "")}
            />
          </div>
          <p className="mt-4 text-xs leading-6 text-mist-400">
            {t.amountsNote}
            <br />
            {t.profileUpdated} · {fmtLocal(profile.data.updated_at)}
          </p>
        </Panel>
      ) : (
        <ClientUnavailable />
      )}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Panel>
          <h2 className="mb-4 font-display text-xl">{t.targetAllocation}</h2>
          {portfolio.data ? (
            <>
              <Allocation allocation={portfolio.data.allocation} />
              <p className="mt-4 text-xs leading-6 text-mist-400">
                {portfolio.data.performance_explanation}
              </p>
              <ButtonLink className="mt-4" href="/client/portfolio" size="sm">
                {t.nav.portfolio}
              </ButtonLink>
            </>
          ) : (
            <ClientUnavailable />
          )}
        </Panel>
        <Panel>
          <h2 className="mb-4 font-display text-xl">{t.riskLevel}</h2>
          {risk.data ? (
            <>
              <Badge tone="gold">{risk.data.level ?? t.unassessed}</Badge>
              <p className="mt-4 text-sm leading-7 text-mist-300">
                {risk.data.explanation}
              </p>
              <ButtonLink
                className="mt-4"
                href="/client/risk-profile"
                size="sm"
              >
                {t.nav.risk}
              </ButtonLink>
            </>
          ) : (
            <ClientUnavailable />
          )}
        </Panel>
      </div>
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl">{t.nav.goals}</h2>
          <ButtonLink href="/client/goals" size="sm">
            {t.nav.goals}
          </ButtonLink>
        </div>
        {goals.data ? (
          <>
            <GoalCards goals={goals.data.goals.slice(0, 2)} />
            <p className="text-xs leading-6 text-mist-400">
              {goals.data.progress_explanation}
            </p>
          </>
        ) : (
          <ClientUnavailable />
        )}
      </section>
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl">{t.recentDocuments}</h2>
          <ButtonLink href="/client/documents" size="sm">
            {t.allDocuments}
          </ButtonLink>
        </div>
        {reports.data ? (
          <ReportList reports={reports.data.reports} />
        ) : (
          <ClientUnavailable />
        )}
      </Panel>
      <Panel>
        <h2 className="mb-3 font-display text-xl">{t.advisor}</h2>
        {advisors.data ? (
          advisors.data.advisors.length ? (
            <ul className="space-y-2 text-sm text-mist-300">
              {advisors.data.advisors.map((advisor) => (
                <li key={advisor.email} className="break-all">
                  {advisor.email}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-mist-400">{t.noAdvisor}</p>
          )
        ) : (
          <ClientUnavailable />
        )}
      </Panel>
    </ClientPage>
  );
}
