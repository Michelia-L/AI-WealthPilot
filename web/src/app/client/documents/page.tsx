import { ClientPage, ReportList } from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import { ButtonLink, Panel } from "@/components/ui";
import { getClientReports } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientDocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const candidate = Number((await searchParams).offset ?? 0);
  const offset =
    Number.isSafeInteger(candidate) && candidate >= 0 ? candidate : 0;
  const limit = 20;
  const t = (await getDict()).clientPortal;
  const { data } = await getClientReports(await getLocale(), offset, limit);
  return (
    <ClientPage section="documents">
      {data ? (
        <>
          <Panel>
            <ReportList reports={data.reports} />
          </Panel>
          <div className="flex flex-wrap gap-3">
            {offset > 0 && (
              <ButtonLink
                href={`/client/documents?offset=${Math.max(0, offset - limit)}`}
                size="sm"
              >
                {t.previous}
              </ButtonLink>
            )}
            {data.reports.length === limit && (
              <ButtonLink
                href={`/client/documents?offset=${offset + limit}`}
                size="sm"
              >
                {t.next}
              </ButtonLink>
            )}
          </div>
        </>
      ) : (
        <ClientUnavailable />
      )}
    </ClientPage>
  );
}
