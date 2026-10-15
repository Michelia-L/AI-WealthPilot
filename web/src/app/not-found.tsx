import { getDict } from "@/lib/i18n/server";
import { ButtonLink, EmptyState } from "@/components/ui";

/** Root 404 — covers both notFound() calls and unmatched URLs app-wide. */
export default async function NotFound() {
  const t = await getDict();
  return (
    <main className="mx-auto max-w-4xl px-5 py-12">
      <EmptyState
        icon="warning"
        title={t.errors.page.notFoundTitle}
        hint={t.errors.page.notFoundHint}
        action={
          <ButtonLink href="/" variant="secondary" size="sm">
            {t.errors.page.backHome}
          </ButtonLink>
        }
      />
    </main>
  );
}
