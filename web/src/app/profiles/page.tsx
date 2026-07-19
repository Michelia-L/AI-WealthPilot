import { detailToPayload, getProfile, getProfiles, getQuestionnaire } from "@/lib/api";
import type { ProfilePayload } from "@/lib/api";
import ProfilesManager from "@/components/profiles/profiles-manager";

export const metadata = {
  title: "客户画像 · AI WealthPilot",
};

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * Client profiles — CRUD over the SQLite-backed API.
 * The list is server-rendered (no-store); the manager client component owns
 * create/edit/delete/import and revalidates via router.refresh().
 * The risk questionnaire is static metadata, fetched alongside the list.
 * ?edit=<id>（来自客户枢纽的深链）由服务端预取该客户并直接进入编辑模式。
 */
export default async function ProfilesPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const editRaw = typeof sp.edit === "string" ? Number(sp.edit) : NaN;
  const initialEditId =
    Number.isInteger(editRaw) && editRaw > 0 ? editRaw : null;

  const [data, questionnaire, editDetail] = await Promise.all([
    getProfiles(),
    getQuestionnaire(),
    initialEditId ? getProfile(initialEditId) : Promise.resolve(null),
  ]);

  const initialEdit: { id: number; payload: ProfilePayload } | null =
    initialEditId && editDetail
      ? { id: initialEditId, payload: detailToPayload(editDetail) }
      : null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <ProfilesManager
        initialProfiles={data?.profiles ?? null}
        questionnaire={questionnaire}
        initialEdit={initialEdit}
      />
    </div>
  );
}
