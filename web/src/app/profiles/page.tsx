import { getProfiles } from "@/lib/api";
import ProfilesManager from "@/components/profiles-manager";

export const metadata = {
  title: "客户画像 · AI WealthPilot",
};

/**
 * Client profiles — CRUD over the SQLite-backed API.
 * The list is server-rendered (no-store); the manager client component owns
 * create/edit/delete/import and revalidates via router.refresh().
 */
export default async function ProfilesPage() {
  const data = await getProfiles();

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          客户画像 <span className="text-base font-normal text-slate-400">Client Profiles</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          IPS 框架客户信息管理：基本信息、财务状况、投资目标与风险评分
        </p>
      </header>

      <ProfilesManager initialProfiles={data?.profiles ?? null} />
    </div>
  );
}
