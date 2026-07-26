"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { LlmSettingsResponse } from "@/lib/api";
import Button from "@/components/ui/button";
import { Badge } from "@/components/ui/chip";
import { Field, Input, Select } from "@/components/ui/field";
import Icon from "@/components/ui/icon";
import Panel from "@/components/ui/panel";

const SOURCE_BADGE: Record<
  LlmSettingsResponse["source"],
  { tone: "gold" | "steel" | "cinnabar"; label: string }
> = {
  db: { tone: "gold", label: "自定义端点" },
  env: { tone: "steel", label: "环境变量" },
  none: { tone: "cinnabar", label: "未配置" },
};

export default function SettingsForm({ initial }: { initial: LlmSettingsResponse }) {
  const router = useRouter();
  const [endpoint, setEndpoint] = useState(initial.source === "db" ? initial.base_url : "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(initial.source === "db" ? initial.model : "");
  const [models, setModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
        throw new Error(typeof data.detail === "string" ? data.detail : `拉取失败（HTTP ${res.status}）`);
      }
      const list = (data.models as string[]) ?? [];
      if (list.length === 0) throw new Error("端点未返回任何可用模型");
      setModels(list);
      if (!list.includes(model)) setModel(list[0]);
      setNotice(`已获取 ${list.length} 个可用模型`);
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
        throw new Error(typeof data.detail === "string" ? data.detail : `保存失败（HTTP ${res.status}）`);
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
          <h3 className="text-sm font-semibold text-mist-100">当前生效配置</h3>
          <Badge tone={source.tone} dot>
            {source.label}
          </Badge>
          {initial.demo && <Badge tone="steel">演示模式</Badge>}
        </div>
        <dl className="grid gap-x-10 gap-y-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="mb-1 text-xs text-mist-500">模型</dt>
            <dd className="font-mono text-mist-100">{initial.model || "—"}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-mist-500">端点</dt>
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
            演示模式（DEMO_MODE=1）优先于一切端点配置 —— AI 功能回放录制样例；关闭后方可用下方自定义端点。
          </p>
        )}
      </Panel>

      {/* ------------------------------ 自定义端点 ------------------------------ */}
      <Panel>
        <h3 className="mb-1.5 text-sm font-semibold text-mist-100">自定义模型端点</h3>
        <p className="mb-6 text-xs leading-5 text-mist-500">
          兼容 OpenAI API 协议的服务均可接入。Key 仅明文保存在本机 SQLite（data/wealthpilot.db），不会上传他处；保存后 AI 顾问 / IPS 生成 / 调仓建议立即切换到新端点。
        </p>

        <div className="grid gap-5 lg:grid-cols-2">
          <Field label="端点地址（Base URL）">
            <Input
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder="https://api.deepseek.com"
              spellCheck={false}
            />
          </Field>
          <Field label="API Key" hint="留空保存 = 清除自定义配置，回退到环境变量">
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
          <Field label="模型" className="min-w-64 flex-1">
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
                placeholder="手动填写，或先拉取模型列表"
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
            {fetching ? "拉取中…" : "拉取模型列表"}
          </Button>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-white/[0.05] pt-5">
          <Button
            size="lg"
            icon="check"
            onClick={() =>
              save(
                { base_url: endpoint.trim(), api_key: apiKey.trim(), model: model.trim() },
                "已保存 —— 全站 AI 功能已切换到自定义端点。"
              )
            }
            disabled={saving || fetching || !endpoint.trim() || !apiKey.trim() || !model.trim()}
          >
            {saving ? "保存中…" : "保存配置"}
          </Button>
          {initial.source === "db" && (
            <Button
              variant="ghost"
              icon="trash"
              onClick={() =>
                save(
                  { base_url: "", api_key: "", model: "" },
                  "已清除自定义配置 —— 回退到环境变量。"
                )
              }
              disabled={saving || fetching}
            >
              清除自定义
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
