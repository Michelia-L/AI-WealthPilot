import { ClientPage, GoalCards } from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import { Panel } from "@/components/ui";
import { getClientGoals } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientGoalsPage() {
  const t = (await getDict()).clientPortal;
  const { data } = await getClientGoals(await getLocale());
  return (
    <ClientPage section="goals">
      {data ? (
        <>
          <GoalCards goals={data.goals} />
          <p className="text-xs text-mist-400">{t.amountsNote}</p>
          <Panel>
            <h2 className="mb-4 font-display text-xl">{t.goalProgress}</h2>
            <p className="text-sm leading-7 text-mist-300">
              {data.progress_explanation}
            </p>
            <p className="mt-3 text-xs leading-6 text-mist-400">
              {t.projectionsUnavailable}
            </p>
          </Panel>
        </>
      ) : (
        <ClientUnavailable />
      )}
    </ClientPage>
  );
}
