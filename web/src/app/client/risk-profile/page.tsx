import { ClientPage } from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import { Badge, Panel } from "@/components/ui";
import { getClientProfile, getClientRisk } from "@/lib/api/server";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientRiskPage() {
  const locale = await getLocale();
  const t = (await getDict()).clientPortal;
  const [risk, profile] = await Promise.all([
    getClientRisk(locale),
    getClientProfile(locale),
  ]);
  return (
    <ClientPage section="risk">
      {risk.data ? (
        <Panel>
          <h2 className="mb-4 font-display text-xl">{t.riskLevel}</h2>
          <Badge tone="gold">{risk.data.level ?? t.unassessed}</Badge>
          <p className="mt-5 text-sm leading-7 text-mist-300">
            {risk.data.explanation}
          </p>
        </Panel>
      ) : (
        <ClientUnavailable />
      )}
      {profile.data ? (
        <Panel>
          <h2 className="mb-5 font-display text-xl">{t.profile}</h2>
          <p className="mb-4 font-medium">{profile.data.name}</p>
          <dl className="grid gap-5 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-mist-400">{t.age}</dt>
              <dd className="mt-2 font-mono">{profile.data.age}</dd>
            </div>
            <div>
              <dt className="text-mist-400">{t.dependents}</dt>
              <dd className="mt-2 font-mono">{profile.data.dependents}</dd>
            </div>
            <div>
              <dt className="text-mist-400">{t.horizon}</dt>
              <dd className="mt-2">
                {t.years(profile.data.time_horizon_years)}
              </dd>
            </div>
          </dl>
          <p className="mt-5 text-xs leading-6 text-mist-400">
            {t.reviewProfile}
          </p>
        </Panel>
      ) : (
        <ClientUnavailable />
      )}
    </ClientPage>
  );
}
