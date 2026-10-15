import { ButtonLink, EmptyState } from "@/components/ui";
import { getDict } from "@/lib/i18n/server";

export default async function ClientNotFound() {
  const t = (await getDict()).clientPortal;
  return (
    <EmptyState
      icon="scroll"
      title={t.missingDocument}
      hint={t.missingDocumentHint}
      action={
        <ButtonLink href="/client/documents">{t.backDocuments}</ButtonLink>
      }
    />
  );
}
