import Markdown from "@/components/markdown";
import { Allocation, ClientPage } from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import { ButtonLink, Panel } from "@/components/ui";
import { getClientPortfolio } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientPortfolioPage() {
  const t = (await getDict()).clientPortal;
  const { data } = await getClientPortfolio(await getLocale());
  return (
    <ClientPage section="portfolio">
      {data ? (
        <>
          <Panel>
            <h2 className="mb-4 font-display text-xl">{t.targetAllocation}</h2>
            <Allocation allocation={data.allocation} />
            {data.report_id && (
              <ButtonLink
                className="mt-5"
                href={`/client/documents/${encodeURIComponent(data.report_id)}`}
                icon="scroll"
              >
                {t.readPlan}
              </ButtonLink>
            )}
          </Panel>
          {data.recommendation && (
            <Panel>
              <h2 className="mb-4 font-display text-xl">{t.recommendation}</h2>
              <Markdown>{data.recommendation}</Markdown>
            </Panel>
          )}
          <Panel>
            <h2 className="mb-4 font-display text-xl">{t.performance}</h2>
            <p className="text-sm leading-7 text-mist-300">
              {data.performance_explanation}
            </p>
            <p className="mt-3 text-xs leading-6 text-mist-400">
              {t.performanceMetrics}
            </p>
          </Panel>
        </>
      ) : (
        <ClientUnavailable />
      )}
    </ClientPage>
  );
}
