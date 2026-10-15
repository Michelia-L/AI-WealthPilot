import ClientAssistant from "@/components/client-portal/assistant";
import { ClientPage } from "@/components/client-portal/sections";
import { getLocale } from "@/lib/i18n/server";

export default async function ClientAIPage() {
  return (
    <ClientPage section="ai">
      <ClientAssistant key={await getLocale()} />
    </ClientPage>
  );
}
