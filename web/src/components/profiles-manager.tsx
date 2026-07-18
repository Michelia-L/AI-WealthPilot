"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type {
  InvestmentGoalInput,
  ProfileDetailResponse,
  ProfilePayload,
  ProfileSummary,
  QuestionnaireQuestion,
  QuestionnaireResponse,
} from "@/lib/api";
import {
  classifyRiskPreview,
  detailToPayload,
  MARITAL_STATUS_OPTIONS,
  scoreFromAnswers,
  TAX_STATUS_OPTIONS,
} from "@/lib/api";
import { fmtLocal, fmtMoney, fmtPct } from "@/lib/format";

const EMPTY_FORM: ProfilePayload = {
  name: "",
  age: 30,
  marital_status: "single",
  dependents: 0,
  financial: {
    annual_income: 0,
    annual_expenses: 0,
    investable_assets: 0,
    total_liabilities: 0,
    emergency_fund_months: 0,
  },
  goals: [],
  time_horizon_years: 10,
  is_multi_stage: false,
  liquidity_needs: 0,
  tax_status: "taxable",
  esg_preference: false,
  sector_restrictions: [],
  notes: "",
  risk_scores: { ability_score: 0, willingness_score: 0 },
  ability_answers: {},
  willingness_answers: {},
};

const RISK_TONES = [
  "bg-emerald-900/60 text-emerald-300",
  "bg-teal-900/60 text-teal-300",
  "bg-amber-900/60 text-amber-300",
  "bg-orange-900/60 text-orange-300",
  "bg-rose-900/60 text-rose-300",
];
const RISK_LEVELS = [
  "Conservative / 保守型",
  "Moderately Conservative / 稳健型",
  "Moderate / 平衡型",
  "Moderately Aggressive / 成长型",
  "Aggressive / 进取型",
];

function riskChip(level: string) {
  const idx = RISK_LEVELS.indexOf(level);
  const tone = idx >= 0 ? RISK_TONES[idx] : "bg-slate-800 text-slate-400";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}>
      {level || "未评估"}
    </span>
  );
}

/* ------------------------------- form atoms ------------------------------ */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

const INPUT_CLS =
  "w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100";

function NumField({
  label,
  value,
  onChange,
  min = 0,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        className={INPUT_CLS}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Math.max(min, parseFloat(e.target.value) || 0))}
      />
    </Field>
  );
}

function PillGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="text-sm text-slate-300">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <div className="flex overflow-hidden rounded-lg border border-slate-700">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={`flex-1 px-2 py-1.5 text-xs font-medium transition-colors ${
              value === o.value
                ? "bg-slate-700 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RiskSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <span className="font-mono text-sm text-slate-100">
          {value === 0 ? "未评估" : value.toFixed(1)}
        </span>
      </span>
      <input
        type="range"
        min={0}
        max={5}
        step={0.5}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-amber-500"
      />
    </label>
  );
}

/** One questionnaire track (ability or willingness): questions + toggleable options. */
function QuestionTrack({
  title,
  questions,
  answers,
  onAnswer,
}: {
  title: string;
  questions: QuestionnaireQuestion[];
  answers: Record<string, string>;
  onAnswer: (questionKey: string, optionKey: string) => void;
}) {
  return (
    <div className="space-y-5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </h4>
      {questions.map((q, qi) => (
        <div key={q.key}>
          <p className="text-sm leading-snug text-slate-200">
            <span className="mr-1.5 font-mono text-xs text-slate-500">{qi + 1}.</span>
            {q.question}
          </p>
          <div className="mt-1.5 space-y-1">
            {q.options.map((o) => {
              const selected = answers[q.key] === o.key;
              return (
                <button
                  key={o.key}
                  type="button"
                  onClick={() => onAnswer(q.key, o.key)}
                  className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-1 text-left text-xs transition-colors ${
                    selected
                      ? "border-amber-500/60 bg-amber-950/40 text-amber-200"
                      : "border-slate-800 text-slate-400 hover:border-slate-600 hover:text-slate-300"
                  }`}
                >
                  <span
                    className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                      selected ? "bg-amber-400" : "bg-slate-700"
                    }`}
                  />
                  {o.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ main component ---------------------------- */

export default function ProfilesManager({
  initialProfiles,
  questionnaire,
}: {
  initialProfiles: ProfileSummary[] | null;
  questionnaire: QuestionnaireResponse | null;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"list" | "create" | "edit">("list");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ProfilePayload>(EMPTY_FORM);
  const [restrictionsText, setRestrictionsText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const set = <K extends keyof ProfilePayload>(key: K, value: ProfilePayload[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));
  const setFin = (key: keyof ProfilePayload["financial"], value: number) =>
    setForm((prev) => ({ ...prev, financial: { ...prev.financial, [key]: value } }));

  /** Toggle a questionnaire answer; clicking the selected option clears it. */
  const setAnswer = (
    track: "ability_answers" | "willingness_answers",
    questionKey: string,
    optionKey: string
  ) =>
    setForm((prev) => {
      const answers = { ...prev[track] };
      if (answers[questionKey] === optionKey) delete answers[questionKey];
      else answers[questionKey] = optionKey;
      return { ...prev, [track]: answers };
    });

  function startCreate() {
    setForm(EMPTY_FORM);
    setRestrictionsText("");
    setEditingId(null);
    setError(null);
    setMode("create");
  }

  async function startEdit(id: number) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/profiles/${id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
      const payload = detailToPayload(data as ProfileDetailResponse);
      setForm(payload);
      setRestrictionsText(payload.sector_restrictions.join(", "));
      setEditingId(id);
      setMode("edit");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const payload: ProfilePayload = {
      ...form,
      name: form.name.trim(),
      sector_restrictions: restrictionsText
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      const res = await fetch(
        mode === "edit" ? `/api/profiles/${editingId}` : "/api/profiles",
        {
          method: mode === "edit" ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((d: { msg?: string }) => d.msg ?? "校验失败").join("；")
              : `保存失败（HTTP ${res.status}）`
        );
      }
      setMode("list");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(`确定删除画像「${name}」？此操作不可撤销。`)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/profiles/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importLegacy() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch("/api/profiles/import", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "导入失败");
      setNotice(
        `导入完成：发现 ${data.files_found} 个 JSON 文件，新增 ${data.imported} 条，跳过 ${data.skipped} 条。`
      );
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const setGoal = <K extends keyof InvestmentGoalInput>(
    idx: number,
    key: K,
    value: InvestmentGoalInput[K]
  ) =>
    setForm((prev) => ({
      ...prev,
      goals: prev.goals.map((g, i) => (i === idx ? { ...g, [key]: value } : g)),
    }));

  /* --------------------------------- form --------------------------------- */

  if (mode !== "list") {
    // Mirror of the server-side precedence: a track with answers derives its
    // score from the questionnaire; an unanswered track keeps manual scores.
    const abilityScore =
      questionnaire && Object.keys(form.ability_answers).length > 0
        ? scoreFromAnswers(questionnaire.ability, form.ability_answers)
        : form.risk_scores.ability_score;
    const willingnessScore =
      questionnaire && Object.keys(form.willingness_answers).length > 0
        ? scoreFromAnswers(questionnaire.willingness, form.willingness_answers)
        : form.risk_scores.willingness_score;
    const preview = classifyRiskPreview(abilityScore, willingnessScore);
    const fmtScore = (v: number) => (v === 0 ? "—" : v.toFixed(1));
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">
            {mode === "edit" ? `编辑画像 · ${form.name || "…"}` : "新建画像"}
          </h2>
          <button
            type="button"
            onClick={() => setMode("list")}
            className="rounded-lg border border-slate-700 px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200"
          >
            取消
          </button>
        </div>

        <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-semibold text-slate-200">基本信息</h3>
          <div className="grid gap-4 md:grid-cols-4">
            <Field label="姓名">
              <input
                className={INPUT_CLS}
                value={form.name}
                placeholder="例如：张三"
                onChange={(e) => set("name", e.target.value)}
              />
            </Field>
            <NumField label="年龄" value={form.age} min={18} max={100}
              onChange={(v) => set("age", Math.min(100, v))} />
            <PillGroup label="婚姻状况" value={form.marital_status}
              options={MARITAL_STATUS_OPTIONS} onChange={(v) => set("marital_status", v)} />
            <NumField label="受抚养人数" value={form.dependents} max={20}
              onChange={(v) => set("dependents", v)} />
          </div>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-semibold text-slate-200">财务状况</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <NumField label="年收入" value={form.financial.annual_income} step={10000}
              onChange={(v) => setFin("annual_income", v)} />
            <NumField label="年支出" value={form.financial.annual_expenses} step={10000}
              onChange={(v) => setFin("annual_expenses", v)} />
            <NumField label="可投资资产" value={form.financial.investable_assets} step={10000}
              onChange={(v) => setFin("investable_assets", v)} />
            <NumField label="总负债" value={form.financial.total_liabilities} step={10000}
              onChange={(v) => setFin("total_liabilities", v)} />
            <NumField label="应急基金（月数）" value={form.financial.emergency_fund_months}
              step={0.5} onChange={(v) => setFin("emergency_fund_months", v)} />
          </div>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">投资目标</h3>
            <button
              type="button"
              onClick={() =>
                set("goals", [
                  ...form.goals,
                  { name: "", target_amount: 0, years: 10, priority: "medium" },
                ])
              }
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
            >
              ➕ 添加目标
            </button>
          </div>
          {form.goals.length === 0 && (
            <p className="text-xs text-slate-500">暂无目标，点击右上角添加。</p>
          )}
          <div className="space-y-3">
            {form.goals.map((g, i) => (
              <div key={i} className="grid items-end gap-3 md:grid-cols-[2fr_1fr_1fr_1fr_auto]">
                <Field label={i === 0 ? "目标名称" : ""}>
                  <input className={INPUT_CLS} value={g.name} placeholder="例如：退休"
                    onChange={(e) => setGoal(i, "name", e.target.value)} />
                </Field>
                <NumField label={i === 0 ? "目标金额" : ""} value={g.target_amount} step={100000}
                  onChange={(v) => setGoal(i, "target_amount", v)} />
                <NumField label={i === 0 ? "年限" : ""} value={g.years} max={80}
                  onChange={(v) => setGoal(i, "years", v)} />
                <PillGroup label={i === 0 ? "优先级" : ""} value={g.priority}
                  options={[
                    { value: "high", label: "高" },
                    { value: "medium", label: "中" },
                    { value: "low", label: "低" },
                  ] as const}
                  onChange={(v) => setGoal(i, "priority", v)} />
                <button
                  type="button"
                  onClick={() => set("goals", form.goals.filter((_, j) => j !== i))}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-500 hover:text-rose-300"
                >
                  🗑️
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-semibold text-slate-200">投资约束与偏好</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <NumField label="投资期限（年）" value={form.time_horizon_years} min={1} max={60}
              onChange={(v) => set("time_horizon_years", Math.max(1, v))} />
            <NumField label="流动性需求（金额）" value={form.liquidity_needs} step={10000}
              onChange={(v) => set("liquidity_needs", v)} />
            <PillGroup label="税务状态" value={form.tax_status} options={TAX_STATUS_OPTIONS}
              onChange={(v) => set("tax_status", v)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="行业限制（逗号分隔）">
              <input className={INPUT_CLS} value={restrictionsText}
                placeholder="例如：烟草, 军工"
                onChange={(e) => setRestrictionsText(e.target.value)} />
            </Field>
            <label className="flex items-end gap-2 pb-1.5 text-sm text-slate-300">
              <input type="checkbox" checked={form.esg_preference}
                onChange={(e) => set("esg_preference", e.target.checked)}
                className="h-4 w-4 accent-amber-500" />
              ESG 偏好（环境/社会/治理）
            </label>
          </div>
          <Field label="备注">
            <textarea className={`${INPUT_CLS} min-h-20`} value={form.notes}
              onChange={(e) => set("notes", e.target.value)} />
          </Field>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-200">风险问卷</h3>
            <span className="text-xs text-slate-500">
              能力 <span className="font-mono text-slate-300">{fmtScore(abilityScore)}</span>
              {" · "}意愿 <span className="font-mono text-slate-300">{fmtScore(willingnessScore)}</span>
              {" → "}综合 = min(能力, 意愿)：<span className="text-amber-300">{preview}</span>
            </span>
          </div>
          {questionnaire ? (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <QuestionTrack
                  title="风险承受能力（客观 · 5 题）"
                  questions={questionnaire.ability}
                  answers={form.ability_answers}
                  onAnswer={(q, o) => setAnswer("ability_answers", q, o)}
                />
                <QuestionTrack
                  title="风险承受意愿（主观 · 4 题）"
                  questions={questionnaire.willingness}
                  answers={form.willingness_answers}
                  onAnswer={(q, o) => setAnswer("willingness_answers", q, o)}
                />
              </div>
              <p className="text-xs text-slate-600">
                已答题目自动算分（未答题不参与平均），保存时覆盖手动评分；再次点击选项可取消作答。全部留空则保留手动评分，0 表示未评估。
              </p>
            </>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <RiskSlider label="风险承受能力" value={form.risk_scores.ability_score}
                  onChange={(v) => set("risk_scores", { ...form.risk_scores, ability_score: v })} />
                <RiskSlider label="风险承受意愿" value={form.risk_scores.willingness_score}
                  onChange={(v) => set("risk_scores", { ...form.risk_scores, willingness_score: v })} />
              </div>
              <p className="text-xs text-slate-600">
                风险问卷加载失败（API 未就绪），暂以手动评分代替；评分为 0 表示未评估。
              </p>
            </>
          )}
        </section>

        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={save}
            disabled={busy || !form.name.trim()}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "保存中…" : mode === "edit" ? "保存修改" : "创建画像"}
          </button>
          {error && <span className="text-sm text-rose-400">⚠ {error}</span>}
        </div>
      </div>
    );
  }

  /* --------------------------------- list --------------------------------- */

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={startCreate}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400"
        >
          ➕ 新建画像
        </button>
        <button
          type="button"
          onClick={importLegacy}
          disabled={busy}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-40"
        >
          📥 从 JSON 导入
        </button>
        {notice && <span className="text-sm text-emerald-400">{notice}</span>}
        {error && <span className="text-sm text-rose-400">⚠ {error}</span>}
      </div>

      {initialProfiles === null ? (
        <div className="rounded-xl border border-rose-900/50 bg-rose-950/30 p-5 text-sm text-rose-300">
          无法获取画像列表 —— 请确认 API 服务已启动。
        </div>
      ) : initialProfiles.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-sm text-slate-500">
          还没有客户画像。点击「新建画像」创建第一个，或从 Streamlit 时代的 JSON 文件导入。
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">姓名</th>
                <th className="px-4 py-3 text-right font-medium">年龄</th>
                <th className="px-4 py-3 font-medium">风险等级</th>
                <th className="px-4 py-3 font-medium">更新时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-slate-900/40">
              {initialProfiles.map((p) => (
                <tr key={p.id} className="text-slate-300">
                  <td className="px-4 py-3 font-medium text-slate-100">{p.name}</td>
                  <td className="px-4 py-3 text-right font-mono">{p.age}</td>
                  <td className="px-4 py-3">{riskChip(p.risk_level)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {fmtLocal(p.updated_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => startEdit(p.id)}
                      disabled={busy}
                      className="mr-2 rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40"
                    >
                      ✏️ 编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(p.id, p.name)}
                      disabled={busy}
                      className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-500 hover:text-rose-300 disabled:opacity-40"
                    >
                      🗑️ 删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
