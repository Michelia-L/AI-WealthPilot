"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { LlmSettingsResponse } from "@/lib/api";
import { useT } from "@/components/locale-context";
import Button from "@/components/ui/button";
import { Badge } from "@/components/ui/chip";
import { Field, Input, Select } from "@/components/ui/field";
import Icon from "@/components/ui/icon";
import Panel from "@/components/ui/panel";

export default function SettingsForm({ initial }: { initial: LlmSettingsResponse }) {
  const router = useRouter();
  const t = useT();
  const [endpoint, setEndpoint] = useState(initial.source === "db" ? initial.base_url : "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(initial.source === "db" ? initial.model : "");
  const [models, setModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const SOURCE_BADGE: Record<
    LlmSettingsResponse["source"],
    { tone: "gold" | "steel" | "cinnabar"; label: string }
  > = {
    db: { tone: "gold", label: t.settings.sourceDb },
    env: { tone: "steel", label: t.settings.sourceEnv },
    none: { tone: "cinnabar", label: t.settings.sourceNone },
  };
  const source = SOURCE_BADGE[initial.source];

  async function fetchModels() {
    setFetching(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch("/api/settings/llm/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: endpoint.trim(), api_key: apiKey.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : t.settings.fetchFailed(res.status));
      }
      const list = (data.models as string[]) ?? [];
      if (list.length === 0) throw new Error(t.settings.noModels);
      setModels(list);
      if (!list.includes(model)) setModel(list[0]);
      setNotice(t.settings.modelsFetched(list.length));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setFetching(false);
    }
  }

  async function save(body: { base_url: string; api_key: string; model: string }, okMessage: string) {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch("/api/settings/llm", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : t.settings.saveFailedHttp(res.status));
      }
      setApiKey("");
      setNotice(okMessage);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 当前生效配置 ------------------------------ */}
      <Panel>
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <h3 className="text-sm font-semibold text-mist-100">{t.settings.currentTitle}</h3>
          <Badge tone={source.tone} dot>
            {source.label}
          </Badge>
          {initial.demo && <Badge tone="steel">{t.settings.demoBadge}</Badge>}
        </div>
        <dl className="grid gap-x-10 gap-y-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="mb-1 text-xs text-mist-500">{t.settings.modelLabel}</dt>
            <dd className="font-mono text-mist-100">{initial.model || "—"}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-mist-500">{t.settings.endpointLabel}</dt>
            <dd className="font-mono break-all text-mist-100">{initial.base_url || "—"}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-mist-500">API Key</dt>
            <dd className="font-mono text-mist-100">{initial.api_key_masked || "—"}</dd>
          </div>
        </dl>
        {initial.demo && (
          <p className="mt-5 flex items-start gap-2.5 rounded-xl border border-steel-500/30 bg-steel-500/[0.06] px-4 py-3 text-sm text-mist-400">
            <Icon name="info" size={15} className="mt-0.5 shrink-0 text-steel-400" />
            {t.settings.demoNotice}
          </p>
        )}
      </Panel>

      {/* ------------------------------ 自定义端点 ------------------------------ */}
      <Panel>
        <h3 className="mb-1.5 text-sm font-semibold text-mist-100">{t.settings.customTitle}</h3>
        <p className="mb-6 text-xs leading-5 text-mist-500">
          {t.settings.customDescription}
        </p>

        <div className="grid gap-5 lg:grid-cols-2">
          <Field label={t.settings.endpointField}>
            <Input
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder="https://api.deepseek.com"
              spellCheck={false}
            />
          </Field>
          <Field label="API Key" hint={t.settings.apiKeyHint}>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </Field>
        </div>

        <div className="mt-5 flex flex-wrap items-end gap-x-5 gap-y-4">
          <Field label={t.settings.modelLabel} className="min-w-64 flex-1">
            {models.length > 0 ? (
              <Select value={model} onChange={(e) => setModel(e.target.value)}>
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={t.settings.modelPlaceholder}
                spellCheck={false}
              />
            )}
          </Field>
          <Button
            variant="secondary"
            icon="refresh"
            onClick={fetchModels}
            disabled={fetching || saving || !endpoint.trim() || !apiKey.trim()}
          >
            {fetching ? t.settings.fetching : t.settings.fetchModels}
          </Button>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-white/[0.05] pt-5">
          <Button
            size="lg"
            icon="check"
            onClick={() =>
              save(
                { base_url: endpoint.trim(), api_key: apiKey.trim(), model: model.trim() },
                t.settings.savedNotice
              )
            }
            disabled={saving || fetching || !endpoint.trim() || !apiKey.trim() || !model.trim()}
          >
            {saving ? t.common.saving : t.settings.saveConfig}
          </Button>
          {initial.source === "db" && (
            <Button
              variant="ghost"
              icon="trash"
              onClick={() =>
                save(
                  { base_url: "", api_key: "", model: "" },
                  t.settings.clearedNotice
                )
              }
              disabled={saving || fetching}
            >
              {t.settings.clearCustom}
            </Button>
          )}
        </div>

        {error && (
          <p className="mt-5 flex items-start gap-2.5 rounded-xl border border-cinnabar-500/25 bg-cinnabar-500/[0.08] px-4 py-3 text-sm text-cinnabar-300">
            <Icon name="warning" size={15} className="mt-0.5 shrink-0 text-cinnabar-400" />
            {error}
          </p>
        )}
        {notice && (
          <p className="mt-5 flex items-start gap-2.5 rounded-xl border border-jade-500/25 bg-jade-500/[0.07] px-4 py-3 text-sm text-jade-300">
            <Icon name="check" size={15} className="mt-0.5 shrink-0 text-jade-400" />
            {notice}
          </p>
        )}
      </Panel>
    </div>
  );
}
