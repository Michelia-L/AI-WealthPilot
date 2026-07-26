import { getLlmSettings } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import SettingsForm from "@/components/settings-form";
import SectionHeader from "@/components/ui/section-header";

export const metadata = {
  title: "设置 · AI WealthPilot",
};

/**
 * Settings — user-defined OpenAI-compatible LLM endpoint. The current
 * effective config is fetched server-side; the form owns fetch-models and
 * save mutations through the same-origin proxy.
 */
export default async function SettingsPage() {
  const settings = await getLlmSettings();

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow="Settings"
        title="设置"
        description="自定义 AI 模型端点：任何 OpenAI 兼容服务（DeepSeek、通义、OpenAI、本地 vLLM/Ollama 等）均可接入，保存后全站 AI 功能即时生效。"
        className="mb-8"
      />

      {settings === null ? (
        <ApiOffline resource="LLM 设置" />
      ) : (
        <SettingsForm initial={settings} />
      )}
    </div>
  );
}
